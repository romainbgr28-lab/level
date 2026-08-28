"""Moteur d'Adaptation LEVEL v2 — Étape 1 (historique par exercice) + Étape 2 (matrice de
décision par exercice).

Code Python pur (pas d'IA, pas de FastAPI/SQLAlchemy) : construit, à partir de l'historique de
séances déjà chargé (voir main.py::_construire_contexte_historique), la fenêtre d'occurrences
passées d'un exercice donné (ou d'un slot suivi via historique_exercice_ids en cas de
substitution), puis évalue cet exercice INDÉPENDAMMENT de tout autre exercice de la séance
(evaluer_exercice) selon la matrice de décision de la spec v2 (cas A à H).

Principe central de ce module : ce fichier ne fait JAMAIS de décision globale de séance (ça
reste le rôle de regles_seance.py) — c'est exactement ce que la spec v2 corrige : une mauvaise
performance sur un exercice est d'abord un signal de CET exercice, jamais automatiquement un
signal de fatigue globale appliqué à tous les autres.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

# Fenêtre historique recommandée par la spec (section 5) : 5 à 10 séances. On retient la borne
# haute par défaut (10) — evaluer_exercice() (Étape 2) décide lui-même combien d'occurrences
# récentes il utilise réellement (2-3 en pratique, cf. section 5 point 3), ce module se contente
# de ne jamais remonter plus loin que cette fenêtre.
FENETRE_OCCURRENCES_DEFAUT = 10


@dataclass
class OccurrenceExercice:
    """Une occurrence réelle de l'exercice (ou d'un exercice lié par substitution, voir
    exercice_id) lors d'une séance passée. `series` est la liste brute telle que persistée dans
    HistoriqueSeance.exercices_realises[].series (poids_kg, repetitions, reps_prevues,
    charge_prevue_kg, rpe_approx) — aucune donnée n'est recalculée ici, y compris les champs
    None (série ancienne, ou reps_prevues/rpe_approx non disponibles) : ils sont transmis tels
    quels, à charge de evaluer_exercice() de décider comment les ignorer proprement (spec
    section 5, cas 6)."""

    date: date
    exercice_id: int
    series: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class HistoriqueExercice:
    """Fenêtre d'historique pour un exercice (ou un slot suivi via historique_exercice_ids).

    - occurrences : les occurrences réelles trouvées, les plus récentes d'abord, jamais plus de
      `fenetre` éléments. Une séance où l'exercice était simplement absent n'y figure pas (elle
      est ignorée, pas comptée comme un échec) — cf. spec section 5 cas 4.
    - jamais_realise : True seulement si aucune occurrence n'a été trouvée dans tout
      l'historique fourni (pas seulement dans la fenêtre) -- distinct d'une fenêtre simplement
      vide par manque de recul récent.
    """

    exercice_id: int
    occurrences: list[OccurrenceExercice] = field(default_factory=list)
    jamais_realise: bool = True

    @property
    def nb_occurrences(self) -> int:
        return len(self.occurrences)


def _as_date(d: Any) -> date:
    return d if isinstance(d, date) else date.fromisoformat(d)


def construire_historique_exercice(
    seances: list[dict[str, Any]],
    exercice_id: int,
    exercice_ids_lies: Optional[set[int]] = None,
    fenetre: int = FENETRE_OCCURRENCES_DEFAUT,
) -> HistoriqueExercice:
    """Construit l'historique d'un exercice à partir d'une liste de séances passées.

    `seances` : liste de dicts au format déjà produit par
    main.py::_construire_contexte_historique (au minimum {"date", "exercices_realises"}), dans
    n'importe quel ordre (retriées ici par date décroissante). Une séance sans
    "exercices_realises" exploitable (ancienne séance, ou absente de la liste) est simplement
    ignorée, jamais une exception.

    `exercice_ids_lies` : autres exercice_id à considérer comme LE MÊME exercice pour cette
    recherche (chaîne de substitution du slot courant, voir Seance.exercices[i].historique_exercice_ids
    et spec section 5 cas 5). Le paramètre est fourni par l'appelant (orchestrateur) : ce module
    reste pur et ne va jamais chercher lui-même la chaîne de substitution du jour.

    `fenetre` : nombre maximal d'occurrences réellement trouvées à conserver (les plus
    récentes). Ne limite jamais la profondeur de RECHERCHE dans `seances` (cas 4 : l'exercice
    peut être absent de plusieurs séances récentes avant d'être retrouvé) — seulement le nombre
    d'occurrences retenues une fois trouvées.
    """
    ids_recherches = {exercice_id} | (exercice_ids_lies or set())

    seances_valides = [s for s in (seances or []) if isinstance(s, dict) and s.get("date")]
    seances_triees = sorted(seances_valides, key=lambda s: _as_date(s["date"]), reverse=True)

    occurrences: list[OccurrenceExercice] = []
    for seance in seances_triees:
        exercices_realises = seance.get("exercices_realises") or []
        if not isinstance(exercices_realises, list):
            continue
        item = next(
            (
                e
                for e in exercices_realises
                if isinstance(e, dict) and e.get("exercice_id") in ids_recherches
            ),
            None,
        )
        if item is None:
            continue  # exercice absent de cette séance : on continue à chercher plus loin (cas 4)
        series = item.get("series")
        occurrences.append(
            OccurrenceExercice(
                date=_as_date(seance["date"]),
                exercice_id=item.get("exercice_id"),
                series=list(series) if isinstance(series, list) else [],
            )
        )
        if len(occurrences) >= fenetre:
            break

    return HistoriqueExercice(
        exercice_id=exercice_id,
        occurrences=occurrences,
        jamais_realise=not occurrences,
    )


# ---------------------------------------------------------------------------
# Étape 2 : matrice de décision par exercice (evaluer_exercice)
# ---------------------------------------------------------------------------

# Seuils exacts de la spec (section 6) — aucun autre seuil métier n'est inventé ici.
SEUIL_RATIO_ATTEINT = 0.95
SEUIL_RATIO_INSUFFISANT = 0.75
SEUIL_RATIO_MARGE = 1.05
RPE_BAS = 5
RPE_HAUT = 8
DELTA_CHARGE_SIGNIFICATIF = 0.025  # +2.5%

PLAFOND_CHARGE_PCT = 10.0  # plafond absolu ±10% (spec section 6)
PROGRESSION_STANDARD_PCT = 5.0
REGRESSION_ECHEC_PCT = -8.0
REGRESSION_CHARGE_REDUITE_PCT = -5.0

# Confiance : valeurs numériques (DecisionExercice.confiance: float) associées aux paliers
# nommés par la spec (section 7). Une seule occurrence ne peut jamais atteindre CONFIANCE_HAUTE ;
# des données incomplètes plafonnent à CONFIANCE_BASSE, jamais une erreur.
CONFIANCE_NULLE = 0.0
CONFIANCE_BASSE = 0.4
CONFIANCE_MOYENNE = 0.6
CONFIANCE_HAUTE = 0.85


@dataclass
class SignalExercice:
    type: str
    valeur: Optional[float]
    poids_evidentiel: float
    detail: str


@dataclass
class DecisionExercice:
    exercice_id: int
    charge_pct: float
    volume_pct: float
    raison: str
    confiance: float
    source: str
    signaux: list[SignalExercice] = field(default_factory=list)
    regle_gagnante: str = "neutre"


def _ratio_reps(occurrence: OccurrenceExercice) -> Optional[float]:
    """Ratio répétitions réalisées / prévues, agrégé sur les séries de l'occurrence ayant les
    deux valeurs exploitables. None si aucune série n'a de prévu exploitable (donnée absente,
    jamais traitée comme 0)."""
    total_prevu = 0
    total_realise = 0
    for s in occurrence.series:
        prevu = s.get("reps_prevues")
        realise = s.get("repetitions")
        if prevu is None or realise is None:
            continue
        total_prevu += prevu
        total_realise += realise
    if total_prevu <= 0:
        return None
    return total_realise / total_prevu


def _rpe_exercice(occurrence: OccurrenceExercice) -> Optional[float]:
    """Moyenne des rpe_approx disponibles pour cette occurrence. None si aucune série n'en
    porte — jamais interprété comme RPE=0 (signal absent, pas une mesure)."""
    valeurs = [s.get("rpe_approx") for s in occurrence.series if s.get("rpe_approx") is not None]
    if not valeurs:
        return None
    return sum(valeurs) / len(valeurs)


def _delta_charge(occurrence: OccurrenceExercice) -> Optional[float]:
    """(charge_realisee - charge_prevue) / charge_prevue. charge_realisee = MAX des poids_kg
    validés (meilleure charge de travail réellement réalisée, même convention que
    main.py::_derniere_charge_reelle) ; charge_prevue = charge_prevue_kg de l'occurrence
    (constante attendue pour toutes les séries d'un même exercice). None si l'un des deux
    manque — jamais une valeur inventée."""
    charges_prevues = [s.get("charge_prevue_kg") for s in occurrence.series if s.get("charge_prevue_kg") is not None]
    charges_realisees = [s.get("poids_kg") for s in occurrence.series if s.get("poids_kg") is not None]
    if not charges_prevues or not charges_realisees:
        return None
    charge_prevue = charges_prevues[0]
    if not charge_prevue:
        return None
    charge_realisee = max(charges_realisees)
    return (charge_realisee - charge_prevue) / charge_prevue


def _plafonner_charge_pct(charge_pct: float) -> float:
    return max(-PLAFOND_CHARGE_PCT, min(PLAFOND_CHARGE_PCT, charge_pct))


def _tendance_signe(ratio: Optional[float], rpe: Optional[float]) -> int:
    """Classification grossière (+1 progression / -1 régression / 0 neutre) utilisée
    UNIQUEMENT pour juger si deux occurrences successives sont cohérentes entre elles (section
    7) — jamais pour décider de la charge elle-même (ça reste le rôle de la matrice complète
    ci-dessous, qui croise systématiquement ratio, RPE et delta_charge)."""
    if ratio is None:
        return 0
    if (ratio >= SEUIL_RATIO_ATTEINT and (rpe is None or rpe <= RPE_BAS)) or ratio > SEUIL_RATIO_MARGE:
        return 1
    if ratio < SEUIL_RATIO_ATTEINT and rpe is not None and rpe >= RPE_HAUT:
        return -1
    return 0


def _confiance(historique: HistoriqueExercice, signaux_complets: bool) -> float:
    if historique.jamais_realise:
        return CONFIANCE_NULLE
    if not signaux_complets:
        return CONFIANCE_BASSE
    if historique.nb_occurrences < 2:
        return CONFIANCE_MOYENNE  # une seule occurrence : jamais "haute" (spec section 7)
    occ0, occ1 = historique.occurrences[0], historique.occurrences[1]
    signe0 = _tendance_signe(_ratio_reps(occ0), _rpe_exercice(occ0))
    signe1 = _tendance_signe(_ratio_reps(occ1), _rpe_exercice(occ1))
    if signe0 != 0 and signe0 == signe1:
        return CONFIANCE_HAUTE  # >= 2 occurrences cohérentes (spec section 7)
    return CONFIANCE_MOYENNE


def evaluer_exercice(historique: HistoriqueExercice) -> DecisionExercice:
    """Évalue un exercice INDÉPENDAMMENT de tout autre exercice de la séance (spec section 2 :
    « un échec localisé sur un exercice ne doit pas être interprété automatiquement comme une
    fatigue globale »). Chaque branche ci-dessous teste la combinaison COMPLÈTE de signaux
    qu'elle requiert (ratio_reps, RPE et/ou delta_charge) — jamais un seul signal isolé qui
    court-circuiterait les autres avant qu'ils n'aient été considérés."""
    if historique.jamais_realise:
        return DecisionExercice(
            exercice_id=historique.exercice_id,
            charge_pct=0.0,
            volume_pct=0.0,
            raison="première fois",
            confiance=CONFIANCE_NULLE,
            source="defaut",
            signaux=[],
            regle_gagnante="jamais_realise",
        )

    occurrence = historique.occurrences[0]
    ratio = _ratio_reps(occurrence)
    rpe = _rpe_exercice(occurrence)
    delta = _delta_charge(occurrence)

    signaux = [
        SignalExercice(
            type="ratio_reps", valeur=ratio, poids_evidentiel=1.0,
            detail="reps réalisées / reps prévues, absent si reps_prevues indisponible" if ratio is None
            else f"{ratio * 100:.0f}% de la cible de répétitions atteinte",
        ),
        SignalExercice(
            type="rpe_exercice", valeur=rpe, poids_evidentiel=1.0,
            detail="aucun rpe_approx disponible pour cet exercice" if rpe is None
            else f"RPE moyen {rpe:.1f} sur les séries de cette occurrence",
        ),
        SignalExercice(
            type="delta_charge", valeur=delta, poids_evidentiel=0.5,
            detail="charge prévue ou réalisée indisponible" if delta is None
            else f"charge réalisée {delta * 100:+.1f}% par rapport à la charge prévue",
        ),
    ]

    signaux_complets = ratio is not None and rpe is not None

    reps_atteintes = ratio is not None and ratio >= SEUIL_RATIO_ATTEINT
    reps_marge = ratio is not None and ratio > SEUIL_RATIO_MARGE
    reps_intermediaire = ratio is not None and SEUIL_RATIO_INSUFFISANT <= ratio < SEUIL_RATIO_ATTEINT
    reps_insuffisantes = ratio is not None and ratio < SEUIL_RATIO_INSUFFISANT
    rpe_bas = rpe is not None and rpe <= RPE_BAS
    rpe_haut = rpe is not None and rpe >= RPE_HAUT
    charge_hausse_significative = delta is not None and delta > DELTA_CHARGE_SIGNIFICATIF
    charge_equivalente = delta is None or abs(delta) <= DELTA_CHARGE_SIGNIFICATIF
    charge_baisse_significative = delta is not None and delta < -DELTA_CHARGE_SIGNIFICATIF

    if reps_atteintes and charge_hausse_significative:
        # Cas F : la charge réellement utilisée devient la référence pour la prochaine cible
        # (mécanisme déjà porté par main.py::_derniere_charge_reelle, qui retient le MAX
        # réellement validé, pas le prévu — voir étape 6). Ici, on décide seulement de
        # l'incrément SUPPLÉMENTAIRE à appliquer par-dessus cette nouvelle référence, plafonné
        # à +5% comme une progression standard : on ne recompte jamais l'écart déjà réalisé.
        charge_pct = PROGRESSION_STANDARD_PCT
        regle_gagnante = "F"
        raison = (
            f"Charge réellement utilisée {delta * 100:+.1f}% au-dessus de la charge prévue, reps atteintes : "
            "cette charge devient la nouvelle référence, progression supplémentaire plafonnée à +5%."
        )
    elif reps_marge and rpe_bas:
        # Cas E : marge sur les reps sans que la charge n'ait bougé (sinon Cas F ci-dessus).
        charge_pct = PROGRESSION_STANDARD_PCT
        regle_gagnante = "E"
        raison = "Répétitions réalisées nettement au-delà de la cible avec un RPE bas : marge de progression disponible."
    elif reps_atteintes and charge_equivalente and rpe_bas:
        charge_pct = PROGRESSION_STANDARD_PCT
        regle_gagnante = "A"
        raison = "Reps atteintes, charge stable, RPE bas : maîtrise facile, progression standard."
    elif reps_atteintes and charge_equivalente and rpe_haut:
        charge_pct = 0.0
        regle_gagnante = "B"
        raison = "Reps atteintes mais RPE élevé : maîtrise coûteuse, je n'augmente pas encore la charge."
    elif reps_intermediaire and rpe_bas:
        charge_pct = 0.0
        regle_gagnante = "C"
        raison = (
            "Reps légèrement sous la cible mais RPE bas : sous-performance sans effort élevé, "
            "probablement un facteur externe. Pas de sanction."
        )
    elif (reps_intermediaire or reps_insuffisantes) and rpe_haut:
        # Cas D : reps non atteintes (zone intermédiaire OU nettement insuffisante) + RPE élevé.
        charge_pct = REGRESSION_ECHEC_PCT
        regle_gagnante = "D"
        raison = "Reps non atteintes et RPE élevé : échec réel, je réduis la charge."
    elif reps_atteintes and charge_baisse_significative and rpe_haut:
        charge_pct = REGRESSION_CHARGE_REDUITE_PCT
        regle_gagnante = "G"
        raison = (
            "Charge réellement utilisée en dessous de la charge prévue, et malgré tout RPE élevé : "
            "je réduis la charge."
        )
    else:
        # Combinaison non couverte explicitement par la matrice (ex: reps nettement
        # insuffisantes sans confirmation d'un RPE élevé, ou RPE modéré 6-7 non tranché par la
        # spec) : jamais de sanction inventée sans signal complet et cohérent -> maintien.
        charge_pct = 0.0
        regle_gagnante = "neutre"
        raison = "Signal insuffisant ou combinaison non couverte explicitement par la matrice : maintien par défaut."

    charge_pct = _plafonner_charge_pct(charge_pct)
    confiance = _confiance(historique, signaux_complets)

    return DecisionExercice(
        exercice_id=historique.exercice_id,
        charge_pct=charge_pct,
        # V1 (spec section 9) : le volume individualisé n'est PAS appliqué au calibrage réel des
        # séries (duree_seance.py reste inchangé). Le champ existe pour la traçabilité ; le cas D
        # évoque conceptuellement "-1 série", une unité discrète non convertible en pourcentage
        # sans inventer une base arbitraire -- volontairement laissé à 0.0 en V1, reporté à V1.1.
        volume_pct=0.0,
        raison=raison,
        confiance=confiance,
        source="adaptation_exercice",
        signaux=signaux,
        regle_gagnante=regle_gagnante,
    )
