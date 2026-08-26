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
    materiel_requis_liste: Optional[list[str]]
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
        "materiel_requis_liste": getattr(exercice, "materiel_requis_liste", None),
        "pattern_mouvement": getattr(exercice, "pattern_mouvement", None),
        "groupe_musculaire_principal": getattr(exercice, "groupe_musculaire_principal", None),
    }


def materiel_compatible(materiel_requis: Optional[str], materiel_disponible: str) -> bool:
    """Heuristique texte libre historique, encore utilisée par la génération de séance
    (main.py::_selectionner_exercices_candidats, volontairement non modifiée par l'Étape 7C)
    et par materiel_compatible_liste() en repli si un exercice n'a pas encore de
    materiel_requis_liste annoté. Un exercice sans matériel (ou "aucun") est toujours
    compatible ; sinon on cherche un recoupement de mots entre le matériel requis par
    l'exercice et le matériel déclaré par l'utilisateur."""
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


# Ce que chaque catégorie de matériel déclarée à l'onboarding (Onboarding.tsx::MATERIELS)
# couvre comme tags matériel normalisés (voir data/annotations_substitution.py pour le
# vocabulaire exact des 50 exercices annotés). "Aucun" et "Poids du corps" ne couvrent aucun
# tag : seuls les exercices sans matériel requis (liste vide) leur sont compatibles.
# "Salle complète" couvre tout. Sémantique OR au sein de materiel_requis_liste : un exercice
# annoté ["barre", "halteres"] est compatible dès que l'UN des deux est couvert.
MATERIEL_ONBOARDING_VERS_TAGS: dict[str, set[str]] = {
    "Aucun": set(),
    "Poids du corps": set(),
    "Haltères": {"halteres"},
    "Salle complète": {
        "ballon",
        "banc",
        "barre",
        "barre_fixe",
        "echelle_rythme",
        "halteres",
        "machine",
        "medicine_ball",
        "mini_haies",
        "plots",
    },
}


def materiel_compatible_liste(candidat: ExerciceDict, materiel_disponible: str) -> bool:
    """Compatibilité matériel pour le remplacement d'exercice (Étape 7C), basée sur
    materiel_requis_liste (tags normalisés) plutôt que sur le texte libre materiel_requis,
    qui produisait des faux négatifs structurels (ex: "Nordic hamstring curl" annoté sans
    matériel requis, mais dont le texte libre "partenaire ou support fixe" ne recoupe aucune
    des 4 valeurs d'onboarding).

    Liste vide ou absente de tags = aucun matériel requis = toujours compatible. Sinon,
    compatible dès qu'au moins un tag requis fait partie de ce que couvre la catégorie de
    matériel déclarée par l'utilisateur (MATERIEL_ONBOARDING_VERS_TAGS ci-dessus).

    Ne remplace PAS materiel_compatible() : la génération de séance (main.py) continue
    d'utiliser le texte libre, volontairement non touchée par cette étape. Si un exercice n'a
    pas encore de materiel_requis_liste annoté (None — ne devrait pas arriver en pratique, les
    50 exercices actuels le sont tous via seed.py), on retombe sur l'ancienne heuristique texte
    libre plutôt que de deviner un comportement pour une donnée absente."""
    tags_requis = candidat.get("materiel_requis_liste")
    if tags_requis is None:
        return materiel_compatible(candidat.get("materiel_requis"), materiel_disponible)
    if not tags_requis:
        return True
    tags_couverts = MATERIEL_ONBOARDING_VERS_TAGS.get(materiel_disponible, set())
    return any(tag in tags_couverts for tag in tags_requis)


def groupe_concerne_par_zone_sensible(groupe_musculaire: str, zones_sensibles: list[str]) -> bool:
    gm = (groupe_musculaire or "").lower()
    return any(zone.lower() in gm for zone in zones_sensibles if zone)


# Poids de score par critère commun, du plus au moins déterminant (cf. priorité demandée :
# pattern_mouvement > groupe_musculaire_principal > pattern_proche > type). Écart volontairement
# large entre paliers pour qu'aucune combinaison de critères inférieurs ne puisse jamais
# dépasser un critère supérieur (pas de calcul de somme ambigu).
_POIDS_PATTERN_MOUVEMENT = 100
_POIDS_GROUPE_MUSCULAIRE_PRINCIPAL = 10
_POIDS_PATTERN_PROCHE = 5
_POIDS_TYPE = 1

# Patterns de mouvement jugés biomécaniquement assez proches d'un pattern donné pour rester
# une alternative acceptable même sans l'égalité stricte de pattern_mouvement (relation
# symétrique — les deux sens sont vérifiés par _pattern_proche). Volontairement vide pour
# l'instant : mieux vaut ne proposer aucune alternative (liste vide, cf. trouver_alternatives)
# que d'en réintroduire une biomécaniquement fausse en devinant une proximité sans expertise
# métier réelle (voir Étape 7C — c'est exactement ce genre de supposition hâtive, ex. "fente
# proche de hinge", qui a produit le bug initial). À peupler plus tard si besoin, avec une
# vraie validation.
PATTERNS_PROCHES: dict[str, set[str]] = {}

# Un candidat n'est retenu comme alternative que s'il partage au moins un de ces critères
# avec l'exercice actuel. "type" seul (ex: deux exercices "force" sans rapport biomécanique,
# comme Développé couché et Hip thrust) est délibérément exclu : voir _est_pertinent.
_CRITERES_PERTINENTS = {"pattern_mouvement", "groupe_musculaire_principal", "pattern_proche"}


def _pattern_proche(pattern_actuel: Optional[str], pattern_candidat: Optional[str]) -> bool:
    if not pattern_actuel or not pattern_candidat:
        return False
    return pattern_candidat in PATTERNS_PROCHES.get(pattern_actuel, set())


def _score_et_criteres(actuel: ExerciceDict, candidat: ExerciceDict) -> tuple[int, list[str]]:
    score = 0
    criteres: list[str] = []

    if actuel.get("pattern_mouvement") and actuel.get("pattern_mouvement") == candidat.get("pattern_mouvement"):
        score += _POIDS_PATTERN_MOUVEMENT
        criteres.append("pattern_mouvement")
    elif _pattern_proche(actuel.get("pattern_mouvement"), candidat.get("pattern_mouvement")):
        score += _POIDS_PATTERN_PROCHE
        criteres.append("pattern_proche")

    if actuel.get("groupe_musculaire_principal") and actuel.get("groupe_musculaire_principal") == candidat.get(
        "groupe_musculaire_principal"
    ):
        score += _POIDS_GROUPE_MUSCULAIRE_PRINCIPAL
        criteres.append("groupe_musculaire_principal")

    if actuel.get("type") and actuel.get("type") == candidat.get("type"):
        score += _POIDS_TYPE
        criteres.append("type")

    return score, criteres


def _est_pertinent(criteres: list[str]) -> bool:
    """Un partage de "type" uniquement (score = +1) n'est jamais suffisant pour qu'un
    candidat soit une alternative valable — voir Étape 7C : Développé couché et Hip thrust
    sont tous deux "force" sans être interchangeables. Il faut au moins un critère
    biomécaniquement significatif (même pattern de mouvement, même groupe musculaire
    principal, ou pattern jugé proche)."""
    return any(c in _CRITERES_PERTINENTS for c in criteres)


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
      2. exclusion des exercices déjà présents dans la séance (contrainte d'unicité — non
         modifiée par l'Étape 7C : si tous les exercices pertinents sont déjà dans la séance,
         résultat = liste vide, aucune réorganisation automatique)
      3. compatibilité matériel avec ce que l'utilisateur a déclaré (materiel_requis_liste,
         voir materiel_compatible_liste — Étape 7C)
      4. exclusion des zones sensibles déclarées
      5. pertinence biomécanique minimale (voir _est_pertinent — Étape 7C) : un candidat qui
         ne partage que "type" avec l'exercice actuel n'est jamais retenu, même à défaut de
         mieux. Si aucun candidat ne passe ce filtre, retourne une liste vide plutôt qu'une
         alternative non pertinente.

    Tri (déterministe) : score décroissant (pattern_mouvement > groupe_musculaire_principal
    > pattern_proche > type), puis nom alphabétique croissant en cas d'égalité — jamais
    d'ordre dépendant de l'ordre d'itération de la bibliothèque.

    Retourne une liste de dicts {"exercice": ExerciceDict, "score": int, "memes_criteres": [...]}.
    """
    candidats = []
    for ex in bibliotheque:
        if ex["id"] == exercice_actuel["id"]:
            continue
        if ex["id"] in exercice_ids_deja_dans_seance:
            continue
        if not materiel_compatible_liste(ex, materiel_disponible):
            continue
        if groupe_concerne_par_zone_sensible(ex.get("groupe_musculaire", ""), zones_sensibles):
            continue
        score, criteres = _score_et_criteres(exercice_actuel, ex)
        if not _est_pertinent(criteres):
            continue
        candidats.append({"exercice": ex, "score": score, "memes_criteres": criteres})

    candidats.sort(key=lambda c: (-c["score"], c["exercice"]["nom"]))
    return candidats
