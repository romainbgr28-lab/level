"""Sélection déterministe d'exercices de remplacement (Étape 7C).

Fonctions pures, sans dépendance FastAPI/SQLAlchemy : elles opèrent sur de
simples dicts (voir `exercice_vers_dict`), pas sur les modèles ORM, pour
rester testables isolément.

Aucune IA n'intervient ici : le classement des alternatives repose
uniquement sur les attributs structurés de la bibliothèque d'exercices.

`materiel_compatible` et `groupe_concerne_par_zone_sensible` vivaient
auparavant dans main.py ; elles sont regroupées ici (source unique de
vérité) et importées par main.py, aussi bien pour la génération de séance
que pour le remplacement d'exercice.
"""

from typing import Any, Optional, TypedDict


class _ExerciceDictRequis(TypedDict):
    id: int
    nom: str


class ExerciceDict(_ExerciceDictRequis, total=False):
    type: str
    groupe_musculaire: str
    materiel_requis: Optional[str]
    pattern_mouvement: Optional[str]
    groupe_musculaire_principal: Optional[str]


def exercice_vers_dict(exercice: Any) -> ExerciceDict:
    """Convertit un ExerciceBibliotheque (ORM) en dict simple, seule frontière
    de ce module avec le monde SQLAlchemy."""
    return {
        "id": exercice.id,
        "nom": exercice.nom,
        "type": exercice.type,
        "groupe_musculaire": exercice.groupe_musculaire,
        "materiel_requis": exercice.materiel_requis,
        "pattern_mouvement": getattr(exercice, "pattern_mouvement", None),
        "groupe_musculaire_principal": getattr(exercice, "groupe_musculaire_principal", None),
    }


def materiel_compatible(materiel_requis: Optional[str], materiel_disponible: str) -> bool:
    """Heuristique simple de compatibilité matériel : un exercice sans matériel (ou
    "aucun") est toujours compatible ; sinon on cherche un recoupement de mots entre
    le matériel requis par l'exercice et le matériel déclaré par l'utilisateur."""
    if not materiel_requis or "aucun" in materiel_requis.lower():
        return True
    if not materiel_disponible:
        return False

    md = materiel_disponible.lower()
    mots_ignores = {"ou", "et", "de", "des", "le", "la", "les", "un", "une", "en", "option", "pour"}
    mots_requis = [
        mot.strip("()., ") for mot in materiel_requis.lower().replace("/", " ").split() if mot.strip("()., ")
    ]
    mots_requis = [mot for mot in mots_requis if mot not in mots_ignores and len(mot) > 2]
    return any(mot in md for mot in mots_requis)


def groupe_concerne_par_zone_sensible(groupe_musculaire: str, zones_sensibles: list[str]) -> bool:
    gm = (groupe_musculaire or "").lower()
    return any(zone.lower() in gm for zone in zones_sensibles if zone)


# Poids de score par critère commun, du plus au moins déterminant (cf. priorité demandée :
# pattern_mouvement > groupe_musculaire_principal > type). Écart volontairement large entre
# paliers pour qu'aucune combinaison de critères inférieurs ne puisse jamais dépasser un
# critère supérieur (pas de calcul de somme ambigu).
_POIDS_PATTERN_MOUVEMENT = 100
_POIDS_GROUPE_MUSCULAIRE_PRINCIPAL = 10
_POIDS_TYPE = 1


def _score_et_criteres(actuel: ExerciceDict, candidat: ExerciceDict) -> tuple[int, list[str]]:
    score = 0
    criteres: list[str] = []

    if actuel.get("pattern_mouvement") and actuel.get("pattern_mouvement") == candidat.get("pattern_mouvement"):
        score += _POIDS_PATTERN_MOUVEMENT
        criteres.append("pattern_mouvement")

    if actuel.get("groupe_musculaire_principal") and actuel.get("groupe_musculaire_principal") == candidat.get(
        "groupe_musculaire_principal"
    ):
        score += _POIDS_GROUPE_MUSCULAIRE_PRINCIPAL
        criteres.append("groupe_musculaire_principal")

    if actuel.get("type") and actuel.get("type") == candidat.get("type"):
        score += _POIDS_TYPE
        criteres.append("type")

    return score, criteres


def trouver_alternatives(
    exercice_actuel: ExerciceDict,
    bibliotheque: list[ExerciceDict],
    exercice_ids_deja_dans_seance: set[int],
    materiel_disponible: str,
    zones_sensibles: list[str],
) -> list[dict]:
    """Filtre puis classe les candidats de remplacement pour `exercice_actuel`.

    Filtres (éliminatoires, dans cet ordre) :
      1. exclusion de l'exercice actuel lui-même
      2. exclusion des exercices déjà présents dans la séance (contrainte d'unicité)
      3. compatibilité matériel avec ce que l'utilisateur a déclaré
      4. exclusion des zones sensibles déclarées

    Tri (déterministe) : score décroissant (pattern_mouvement > groupe_musculaire_principal
    > type), puis nom alphabétique croissant en cas d'égalité — jamais d'ordre dépendant de
    l'ordre d'itération de la bibliothèque.

    Retourne une liste de dicts {"exercice": ExerciceDict, "score": int, "memes_criteres": [...]}.
    """
    candidats = []
    for ex in bibliotheque:
        if ex["id"] == exercice_actuel["id"]:
            continue
        if ex["id"] in exercice_ids_deja_dans_seance:
            continue
        if not materiel_compatible(ex.get("materiel_requis"), materiel_disponible):
            continue
        if groupe_concerne_par_zone_sensible(ex.get("groupe_musculaire", ""), zones_sensibles):
            continue
        score, criteres = _score_et_criteres(exercice_actuel, ex)
        candidats.append({"exercice": ex, "score": score, "memes_criteres": criteres})

    candidats.sort(key=lambda c: (-c["score"], c["exercice"]["nom"]))
    return candidats
