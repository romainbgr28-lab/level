"""Adaptation d'une séance DÉJÀ générée à une contrainte annoncée en cours de route.

Distinct des modules voisins, et volontairement :
- ``duree_seance.calibrer_exercices`` calibre un plan AVANT génération, à partir d'objets
  ORM ``ExerciceBibliotheque`` fraîchement sélectionnés ;
- ``adaptation_exercice`` décide d'une progression de CHARGE à partir de l'historique ;
- ``regles_seance`` recommande un type de séance et un ajustement global.

Ici, on part d'une séance existante (``Seance.exercices``, liste d'items déjà persistée avec
ses charges, reps et notes) et on la réduit pour tenir dans une contrainte : moins de temps,
moins de matériel, ou de la fatigue. Ce module est PUR (aucune I/O, aucune base, aucun appel
IA) : il reçoit les items de la séance et les métadonnées d'exercices dont il a besoin, et
renvoie la nouvelle liste d'items plus une explication de ce qui a changé.

C'est ici, et pas dans le LLM, que se décide ce qu'on garde et ce qu'on coupe (spécification
V0 section 18 : le LLM interprète et explique, le moteur décide).

Principe de priorité, appliqué partout ci-dessous : on coupe d'abord le volume (séries),
jamais en dessous de ``duree_seance.SERIES_MIN`` ; si ça ne suffit pas, on retire des
exercices en commençant par les MOINS prioritaires. La priorité d'un exercice suit son ordre
dans la séance (le moteur de génération place les exercices principaux en premier), à une
exception près, héritée de ``duree_seance.calibrer_exercices`` : le dernier exercice de la
liste (conventionnellement le gainage/prévention de fin de séance) est protégé tant qu'il
reste plus d'un exercice.
"""

from typing import Any, Optional

import duree_seance
import substitution

# Réduction de volume appliquée quand l'utilisateur déclare une fatigue importante. Valeur
# alignée sur le plafond de fatigue déjà utilisé par le moteur d'adaptation par exercice
# (composition_decision.PLAFOND_FATIGUE_PCT borne la CHARGE) : ici c'est le VOLUME qui baisse,
# la charge n'est jamais touchée par ce module — elle appartient à adaptation_exercice.
SERIES_RETIREES_FATIGUE = 1

# Type d'exercice par défaut quand la bibliothèque ne renseigne rien : c'est celui qui donne
# le temps de repos médian (voir duree_seance.REPOS_SECONDES_DEFAUT), donc l'estimation la
# moins fausse possible plutôt qu'un exercice supposé rapide.
TYPE_EXERCICE_DEFAUT = "force"


class _ExercicePourDuree:
    """Adaptateur minimal : ``duree_seance`` attend des objets exposant ``.type``.

    Évite de dupliquer le calcul de durée (échauffement + exécution + repos) ici : on
    réutilise strictement ``duree_seance._duree_totale_min`` / ``duree_totale_estimee_min``,
    seule définition du temps d'une séance dans le projet.
    """

    __slots__ = ("type",)

    def __init__(self, type_exercice: Optional[str]):
        self.type = type_exercice or TYPE_EXERCICE_DEFAUT


def _plan_depuis_items(
    items: list[dict[str, Any]], meta_par_id: dict[int, dict[str, Any]]
) -> list[dict[str, Any]]:
    return [
        {
            "exercice": _ExercicePourDuree((meta_par_id.get(item.get("exercice_id")) or {}).get("type")),
            "series": int(item.get("series") or duree_seance.SERIES_PAR_DEFAUT),
            "item": item,
        }
        for item in items
    ]


def duree_estimee_min(items: list[dict[str, Any]], meta_par_id: dict[int, dict[str, Any]]) -> int:
    """Durée estimée d'une liste d'items de séance, avec la même formule que la génération."""
    return duree_seance.duree_totale_estimee_min(_plan_depuis_items(items, meta_par_id))


def _nom(item: dict[str, Any], meta_par_id: dict[int, dict[str, Any]]) -> str:
    meta = meta_par_id.get(item.get("exercice_id")) or {}
    return meta.get("nom") or f"Exercice #{item.get('exercice_id')}"


def adapter_pour_duree(
    items: list[dict[str, Any]],
    meta_par_id: dict[int, dict[str, Any]],
    minutes_disponibles: int,
) -> dict[str, Any]:
    """Réduit la séance pour tenir dans ``minutes_disponibles``.

    Renvoie ``{exercices, duree_avant_min, duree_apres_min, series_reduites,
    exercices_retires, changements}``. ``exercices`` est la nouvelle liste d'items, chaque
    item conservé à l'identique sauf son champ ``series`` : charges, reps, notes et
    ``historique_exercice_ids`` ne sont jamais réécrits (la vérité de ce qui était prévu pour
    cet exercice ne change pas parce qu'on en fait moins aujourd'hui).

    Ne fait que réduire : une séance qui tient déjà dans le temps disponible est renvoyée
    telle quelle (on n'invente pas du volume supplémentaire parce qu'il reste des minutes).
    """
    plan = _plan_depuis_items(items, meta_par_id)
    duree_avant = duree_seance.duree_totale_estimee_min(plan)

    if not plan or minutes_disponibles is None:
        return {
            "exercices": list(items),
            "duree_avant_min": duree_avant,
            "duree_apres_min": duree_avant,
            "series_reduites": 0,
            "exercices_retires": [],
            "changements": [],
        }

    series_reduites = 0
    # 1) Volume d'abord : on retire une série à la fois, en commençant par les exercices les
    # moins prioritaires (fin de liste), pour préserver le travail principal du jour.
    while (
        duree_seance._duree_totale_min(plan) > minutes_disponibles
        and any(p["series"] > duree_seance.SERIES_MIN for p in plan)
    ):
        for p in reversed(plan):
            if p["series"] > duree_seance.SERIES_MIN:
                p["series"] -= 1
                series_reduites += 1
                break

    # 2) Puis le nombre d'exercices, en protégeant le dernier (gainage/prévention), exactement
    # comme duree_seance.calibrer_exercices le fait à la génération.
    exercices_retires: list[str] = []
    while len(plan) > 1 and duree_seance._duree_totale_min(plan) > minutes_disponibles:
        retire = plan.pop(-2 if len(plan) > 1 else -1)
        exercices_retires.append(_nom(retire["item"], meta_par_id))

    exercices = [{**p["item"], "series": p["series"]} for p in plan]
    duree_apres = duree_seance.duree_totale_estimee_min(plan)

    changements: list[str] = []
    if series_reduites:
        changements.append(f"{series_reduites} série(s) retirée(s) pour tenir en {minutes_disponibles} min.")
    if exercices_retires:
        changements.append(
            "Exercice(s) retiré(s), les moins prioritaires de la séance : " + ", ".join(exercices_retires) + "."
        )
    if not changements:
        changements.append(f"La séance tient déjà en {minutes_disponibles} min, rien à retirer.")

    return {
        "exercices": exercices,
        "duree_avant_min": duree_avant,
        "duree_apres_min": duree_apres,
        "series_reduites": series_reduites,
        "exercices_retires": exercices_retires,
        "changements": changements,
    }


def adapter_pour_fatigue(
    items: list[dict[str, Any]], meta_par_id: dict[int, dict[str, Any]]
) -> dict[str, Any]:
    """Réduit le VOLUME de la séance suite à une fatigue déclarée, sans toucher aux charges.

    La charge relève d'``adaptation_exercice`` (qui décide à partir de l'historique réel, pas
    d'une déclaration ponctuelle) : une fatigue annoncée aujourd'hui allège la séance du jour,
    elle ne réécrit pas la progression de charge de l'utilisateur.
    """
    plan = _plan_depuis_items(items, meta_par_id)
    duree_avant = duree_seance.duree_totale_estimee_min(plan)

    series_reduites = 0
    for p in plan:
        nouvelles = max(p["series"] - SERIES_RETIREES_FATIGUE, duree_seance.SERIES_MIN)
        series_reduites += p["series"] - nouvelles
        p["series"] = nouvelles

    exercices = [{**p["item"], "series": p["series"]} for p in plan]
    changements = (
        [f"Volume allégé : {series_reduites} série(s) en moins, charges inchangées."]
        if series_reduites
        else ["Le volume est déjà au minimum, rien à retirer sans vider la séance."]
    )
    return {
        "exercices": exercices,
        "duree_avant_min": duree_avant,
        "duree_apres_min": duree_seance.duree_totale_estimee_min(plan),
        "series_reduites": series_reduites,
        "exercices_retires": [],
        "changements": changements,
    }


def exercices_incompatibles_materiel(
    items: list[dict[str, Any]],
    meta_par_id: dict[int, dict[str, Any]],
    materiel_disponible: str,
) -> list[int]:
    """Ids des exercices de la séance que le matériel déclaré ne permet plus.

    Réutilise strictement ``substitution.materiel_compatible_liste`` : c'est la seule
    définition de « faisable avec ce matériel » du projet, celle qui sert déjà à proposer des
    alternatives (``/api/seance/{id}/exercices/{id}/alternatives``).
    """
    incompatibles: list[int] = []
    for item in items:
        exercice_id = item.get("exercice_id")
        meta = meta_par_id.get(exercice_id)
        if meta is None:
            continue
        if not substitution.materiel_compatible_liste(meta, materiel_disponible):
            incompatibles.append(exercice_id)
    return incompatibles
