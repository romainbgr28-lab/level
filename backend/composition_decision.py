"""Moteur d'Adaptation LEVEL v2 — Étape 3 : composition séance + exercice.

Code Python pur (pas d'IA, pas de FastAPI/SQLAlchemy) : combine une DecisionSeance (contexte
global — fatigue, deload, calendrier, cf. regles_seance.py) et une DecisionExercice (signal
propre à un exercice, cf. adaptation_exercice.evaluer_exercice) en une DecisionFinaleExercice.

Principe central (spec v2 section 8) : PAS DE DOUBLE COMPTAGE. La décision globale et la
décision individuelle ne sont jamais additionnées — seule une composition explicite (identité en
séance normale, plafond en fatigue élevée, écrasement en deload) les combine, et ce module
n'introduit AUCUNE règle métier qui ne soit pas déjà définie dans la spec.

Note d'architecture (Étape 3, ne touche pas moteur_decision.py) : `DecisionSeance` est défini
ICI plutôt que dans regles_seance.py — c'est composition_decision.py qui en a besoin en premier
pour composer(), et moteur_decision.py (Étape 4) l'importera d'ici plutôt que de le redéfinir,
pour ne jamais dupliquer ce contrat de données.
"""

from dataclasses import dataclass, field
from typing import Optional

from adaptation_exercice import DecisionExercice

# Plafond de progression appliqué en cas de fatigue globale élevée (spec section 8, cas 2) :
# une progression individuelle est plafonnée à ce niveau, mais une régression individuelle
# n'est JAMAIS adoucie (voir composer() : le plafond n'agit que via un min(), qui laisse
# toujours passer une valeur déjà plus basse).
PLAFOND_FATIGUE_PCT = 2.0


@dataclass
class DecisionSeance:
    """Contexte global de la séance (phénomènes qui concernent TOUTE la séance, jamais un
    exercice isolé) — voir regles_seance.py pour le calcul de ces valeurs, non dupliqué ici.

    `charge_pct` : ajout validé par rapport à la spec initiale — magnitude de charge décidée au
    niveau séance (essentiellement la magnitude du deload, ex. -15.0 ; sans deload ni signal de
    charge global, reste à 0.0 et n'intervient alors jamais dans la composition, cf. règle 3
    "séance normale : le signal séance ne modifie pas la charge individuelle").
    `fatigue_globale` : "normale" | "elevee" | "critique".
    """

    type_seance: str
    intensite_max: str
    deload_actif: bool
    fatigue_globale: str
    jours_ecart: Optional[int]
    volume_global_pct: float
    charge_pct: float
    exclusions: list[str] = field(default_factory=list)
    raisons: list[str] = field(default_factory=list)
    confiance: float = 0.5
    source: str = "regles_seance"


@dataclass
class DecisionFinaleExercice:
    exercice_id: int
    charge_pct: float
    volume_pct: float
    charge_cible_kg: Optional[float]
    series_cible: int
    raison: str
    confiance: float
    source: str
    decision_seance: DecisionSeance
    decision_exercice: Optional[DecisionExercice]
    garde_fou_applique: Optional[str] = None


def _decision_exercice_neutre(exercice_id: int) -> DecisionExercice:
    """Décision neutre explicite pour un exercice sans DecisionExercice disponible (spec
    section 5 cas 1, même contrat que adaptation_exercice.evaluer_exercice pour "jamais
    réalisé") — jamais une exception, jamais une valeur devinée."""
    return DecisionExercice(
        exercice_id=exercice_id,
        charge_pct=0.0,
        volume_pct=0.0,
        raison="aucune décision individuelle disponible pour cet exercice : comportement neutre",
        confiance=0.0,
        source="defaut",
        signaux=[],
        regle_gagnante="neutre",
    )


def composer(
    decision_seance: DecisionSeance,
    decision_exercice: Optional[DecisionExercice],
    exercice_id: int,
    charge_reference_kg: Optional[float] = None,
    series_cible: int = 0,
) -> DecisionFinaleExercice:
    """Compose la décision finale d'UN exercice à partir du contexte séance et de sa propre
    décision individuelle. Fonction pure, appelée une fois par exercice : aucun état partagé
    entre deux appels, aucune mutation des arguments reçus (dataclasses traitées en lecture
    seule) — c'est ce qui garantit qu'un exercice ne peut jamais en contaminer un autre.

    `charge_reference_kg` : dernière charge réellement réalisée pour cet exercice (voir
    main.py::_derniere_charge_reelle, câblée à l'Étape 6 — pas recalculée ici). None si aucun
    historique de charge exploitable (exercice jamais réalisé, ou poids du corps) : dans ce cas
    `charge_cible_kg` reste None, le mécanisme charge_depart existant prend le relais ailleurs.

    `series_cible` : nombre de séries déjà calibré GLOBALEMENT pour toute la séance (spec
    section 9 : le volume n'est PAS individualisé en V1) — simple valeur transmise telle quelle,
    jamais recalculée ni modifiée ici en fonction de l'exercice.
    """
    decision_exercice_effective = decision_exercice if decision_exercice is not None else _decision_exercice_neutre(exercice_id)
    charge_pct_exercice = decision_exercice_effective.charge_pct
    garde_fou_applique: Optional[str] = None
    raison_composition = decision_exercice_effective.raison

    if decision_seance.deload_actif:
        # Règle 1 (spec section 8, cas 3) : le deload domine, MAIS une régression individuelle
        # déjà plus sévère que le deload n'est jamais adoucie -> min() des deux magnitudes.
        # Exemple : exercice déjà à -20% et deload à -15% -> min(-20, -15) = -20, conservé.
        charge_pct_final = min(charge_pct_exercice, decision_seance.charge_pct)
        volume_pct_final = decision_seance.volume_global_pct  # la nuance individuelle de volume est suspendue
        if charge_pct_final != charge_pct_exercice or volume_pct_final != decision_exercice_effective.volume_pct:
            garde_fou_applique = "deload"
            raison_composition = (
                f"{decision_exercice_effective.raison} — semaine de décharge active : "
                f"charge et volume alignés sur la décision de séance ({decision_seance.charge_pct:+.0f}%)."
            )
    elif decision_seance.fatigue_globale == "elevee":
        # Règle 2 (spec section 8, cas 2) : plafond de progression, jamais d'adoucissement
        # d'une régression -> min() suffit : min(+5, +2)=+2, min(-8, +2)=-8 (inchangé).
        charge_pct_final = min(charge_pct_exercice, PLAFOND_FATIGUE_PCT)
        volume_pct_final = decision_exercice_effective.volume_pct  # volume reste global/non individualisé en V1
        if charge_pct_final != charge_pct_exercice:
            garde_fou_applique = "plafond_fatigue"
            raison_composition = (
                f"{decision_exercice_effective.raison} — fatigue globale élevée : progression plafonnée à +{PLAFOND_FATIGUE_PCT:.0f}%."
            )
    else:
        # Règle 3 (spec section 8, cas 1) : séance normale, le signal séance ne modifie pas la
        # charge individuelle -> identité stricte.
        charge_pct_final = charge_pct_exercice
        volume_pct_final = decision_exercice_effective.volume_pct

    # Règle 4 : garde-fou de sécurité — jamais d'augmentation induite par la composition.
    # Invariant garanti structurellement (pas besoin d'assertion runtime) : les deux branches
    # deload/fatigue n'utilisent que min(charge_pct_exercice, plafond), qui ne peut jamais
    # renvoyer une valeur supérieure à charge_pct_exercice ; la branche séance normale renvoie
    # charge_pct_exercice inchangé. La composition ne peut donc jamais augmenter une charge
    # au-delà de ce que l'exercice avait déjà obtenu seul.

    charge_cible_kg = charge_reference_kg * (1 + charge_pct_final / 100) if charge_reference_kg is not None else None

    return DecisionFinaleExercice(
        exercice_id=exercice_id,
        charge_pct=charge_pct_final,
        volume_pct=volume_pct_final,
        charge_cible_kg=charge_cible_kg,
        series_cible=series_cible,
        raison=raison_composition,
        confiance=decision_exercice_effective.confiance,
        source=decision_exercice_effective.source,
        decision_seance=decision_seance,
        decision_exercice=decision_exercice,
        garde_fou_applique=garde_fou_applique,
    )
