"""Calibrage de la durée d'une séance à partir du temps disponible déclaré.

Code Python pur (pas d'IA) : calcule des durées types par exercice (échauffement +
exécution + repos selon le type d'exercice — repos long pour force lourde, repos
court pour gainage/technique) puis réduit series/exercices AVANT l'appel à Mistral
pour que le total estimé ne dépasse pas temps_dispo. Mistral ne décide jamais seul
de la coupe : il reçoit une liste déjà calibrée en temps (nombre de séries et temps
de repos fixés par ce module).
"""

import re
from typing import Any, Optional

DUREE_ECHAUFFEMENT_MIN = 8

# Temps de repos "type" après une série, en secondes, selon le type d'exercice de la
# bibliothèque : repos long pour force lourde / explosivité, repos court pour
# gainage / technique / mobilité.
REPOS_SECONDES_PAR_TYPE: dict[str, int] = {
    "force": 120,
    "force_esthetique": 90,
    "explosivite": 150,
    "vitesse": 120,
    "agilité": 90,
    "technique": 60,
    "esthetique": 60,
    "gainage_prevention": 45,
    "mobilite_recuperation": 30,
    "endurance": 45,
    "échauffement": 20,
}
REPOS_SECONDES_DEFAUT = 90

DUREE_EXECUTION_SECONDES_PAR_SERIE = 40  # temps moyen d'exécution d'une série, hors repos

SERIES_PAR_DEFAUT = 3
SERIES_MIN = 2

# RPE cible indicatif selon l'intensité maximale calculée par le moteur de règles
# (regles_seance.PHASES_INTENSITE) : sert à pré-remplir series_loggees.rpe_cible.
RPE_CIBLE_PAR_INTENSITE: dict[str, int] = {
    "récupération": 4,
    "activation_légère": 5,
    "modérée_technique": 6,
    "normale": 7,
}
RPE_CIBLE_DEFAUT = 7


def repos_recommande_secondes(type_exercice: str) -> int:
    return REPOS_SECONDES_PAR_TYPE.get(type_exercice, REPOS_SECONDES_DEFAUT)


def rpe_cible_pour_intensite(intensite_max: Optional[str]) -> int:
    return RPE_CIBLE_PAR_INTENSITE.get(intensite_max or "", RPE_CIBLE_DEFAUT)


def parser_temps_dispo_minutes(temps_dispo: Optional[str]) -> Optional[int]:
    """Extrait un nombre de minutes depuis un texte libre ("45 min", "1h", "1h30",
    "1 heure"). Retourne None si rien d'exploitable : dans ce cas aucune contrainte
    de temps n'est appliquée (comportement inchangé)."""
    if not temps_dispo:
        return None
    txt = temps_dispo.strip().lower()

    heures_minutes = re.search(r"(\d+)\s*h\D*(\d+)", txt)
    if heures_minutes:
        return int(heures_minutes.group(1)) * 60 + int(heures_minutes.group(2))

    heures = re.search(r"(\d+)\s*h(?:eure)?s?(?!\w)", txt)
    if heures:
        return int(heures.group(1)) * 60

    minutes = re.search(r"(\d+)", txt)
    if minutes:
        return int(minutes.group(1))

    return None


def _duree_exercice_min(nb_series: int, type_exercice: str) -> float:
    repos_s = repos_recommande_secondes(type_exercice)
    total_s = nb_series * DUREE_EXECUTION_SECONDES_PAR_SERIE + max(nb_series - 1, 0) * repos_s
    return total_s / 60


def _duree_totale_min(plan: list[dict[str, Any]]) -> float:
    return DUREE_ECHAUFFEMENT_MIN + sum(_duree_exercice_min(item["series"], item["exercice"].type) for item in plan)


def calibrer_exercices(candidats: list, temps_dispo_min: Optional[int]) -> list[dict[str, Any]]:
    """Construit, pour chaque exercice candidat, un plan {"exercice", "series",
    "temps_repos_recommande_s"}, puis réduit d'abord le nombre de séries (jamais en
    dessous de SERIES_MIN) et, si ça ne suffit pas, le nombre d'exercices (jamais le
    dernier de la liste, conventionnellement le gainage_prevention de fin de séance),
    jusqu'à ce que la durée totale estimée (échauffement + exécution + repos) tienne
    dans temps_dispo_min. Sans temps_dispo déclaré, renvoie le plan par défaut."""
    plan = [
        {
            "exercice": ex,
            "series": SERIES_PAR_DEFAUT,
            "temps_repos_recommande_s": repos_recommande_secondes(ex.type),
        }
        for ex in candidats
    ]

    if temps_dispo_min is None or not plan:
        return plan

    while _duree_totale_min(plan) > temps_dispo_min and any(p["series"] > SERIES_MIN for p in plan):
        for p in plan:
            if p["series"] > SERIES_MIN:
                p["series"] -= 1
                break

    while len(plan) > 1 and _duree_totale_min(plan) > temps_dispo_min:
        del plan[-2]  # on retire l'avant-dernier : le dernier reste réservé au gainage_prevention

    return plan


def duree_totale_estimee_min(plan: list[dict[str, Any]]) -> int:
    return round(_duree_totale_min(plan))
