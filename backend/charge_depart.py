"""Estimation d'une charge de départ raisonnable pour les exercices avec charge,
calculée en code Python pur (pas par Mistral) à partir du poids de corps et du
niveau déclaré à l'onboarding.

N'est utilisée par main.py que tant qu'aucun historique réel (séries loguées,
voir models.SerieLoggee) n'existe pour l'exercice concerné : dès qu'un historique
existe, la vraie progression (regles_seance.py) prend le relais et cette
estimation est ignorée.
"""

import math
from typing import Optional

# Ratio conservateur (charge / poids de corps) par exercice et par niveau déclaré.
# Ces ratios ne visent pas une charge "maximale possible" mais un point de départ
# prudent pour une première séance en salle, à ajuster ensuite selon le ressenti.
# Clés de RATIOS : mot-clé identifiant l'exercice par son nom (voir _identifier_exercice).
RATIOS_PAR_EXERCICE: dict[str, dict[str, float]] = {
    "squat": {"débutant": 0.5, "intermédiaire": 0.75, "avancé": 1.0},
    "hip thrust": {"débutant": 0.5, "intermédiaire": 0.8, "avancé": 1.1},
    "développé": {"débutant": 0.3, "intermédiaire": 0.5, "avancé": 0.75},
    "rowing": {"débutant": 0.3, "intermédiaire": 0.45, "avancé": 0.6},
    "fente": {"débutant": 0.15, "intermédiaire": 0.25, "avancé": 0.35},
}

NIVEAUX_CONNUS = {"débutant", "intermédiaire", "avancé"}


def _identifier_exercice(nom_exercice: str) -> Optional[str]:
    """Fait correspondre le nom d'un exercice de la bibliothèque à une clé de
    RATIOS_PAR_EXERCICE via une recherche de mot-clé insensible à la casse."""
    nom = (nom_exercice or "").lower()
    for cle in RATIOS_PAR_EXERCICE:
        if cle in nom:
            return cle
    return None


def _arrondir_2_5(charge: float) -> float:
    return round(charge / 2.5) * 2.5


def estimer_charge_depart(
    nom_exercice: str,
    poids_corps: Optional[float],
    niveau_declare: Optional[str],
) -> Optional[float]:
    """Calcule une charge de départ (kg) pour un exercice avec charge, ou None si
    l'exercice n'est pas concerné (pas dans RATIOS_PAR_EXERCICE) ou si les données
    nécessaires (poids de corps, niveau) sont indisponibles.

    Arrondie aux 2.5kg les plus proches pour rester réaliste en salle (disques
    disponibles), avec un minimum de 2.5kg (jamais 0 ni négatif).
    """
    if not poids_corps or poids_corps <= 0:
        return None

    cle_exercice = _identifier_exercice(nom_exercice)
    if cle_exercice is None:
        return None

    niveau = (niveau_declare or "").strip().lower()
    if niveau not in NIVEAUX_CONNUS:
        niveau = "débutant"  # repli prudent si niveau non renseigné/reconnu

    ratio = RATIOS_PAR_EXERCICE[cle_exercice][niveau]
    charge = _arrondir_2_5(poids_corps * ratio)
    return max(charge, 2.5)


def formater_recommandation_charge(charge_kg: Optional[float]) -> Optional[str]:
    """Formate la charge estimée pour injection dans le prompt Mistral."""
    if charge_kg is None:
        return None
    charge_txt = f"{charge_kg:g}"
    return (
        f"charge de départ recommandée : {charge_txt} kg, base-toi dessus, "
        "n'invente pas une valeur différente sans raison"
    )
