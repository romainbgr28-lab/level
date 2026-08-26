"""Moteur de règles pour la génération de séances de sport.

Code Python pur, sans appel IA : calcule une recommandation structurée à partir
du profil et de l'historique. Cette recommandation sert ensuite de contexte
contraignant envoyé à Mistral (voir main.py / mistral_client.py) pour générer
la séance concrète.
"""

from datetime import date, timedelta
from typing import Any, Optional

import user_model_v2

JOURS_SEMAINE = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

# Onboarding (src/screens/Onboarding.tsx) collecte les jours disponibles sous forme abrégée
# ("Lun", "Mar", ...), et generer_programme (main.py) construit contraintes_temps et
# gabarit_hebdomadaire avec ces mêmes abréviations comme clés — distinct de JOURS_SEMAINE
# ci-dessus (noms complets), utilisé uniquement pour calendrier_matchs.jour_habituel. Ne pas
# confondre les deux listes lors d'un lookup par date.today().weekday().
JOURS_SEMAINE_ABBREV = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]

PHASES_INTENSITE = {
    "lendemain_match": "récupération",
    "veille_match": "activation_légère",
    "approche_match": "modérée_technique",
    "phase_normale": "normale",
}

# Déplacé vers user_model_v2.PRIORITES_PAR_SPORT (Phase 6 : suppression du hardcoding
# football — le système raisonne via contexte_sportif.sport, avec fallback générique pour
# tout sport non couvert). Alias conservé pour compatibilité de lecture directe éventuelle.
PRIORITES_POSTE = user_model_v2.PRIORITES_PAR_SPORT.get("football", {})

# Groupes musculaires typiquement sollicités par type de séance — utilisé par
# appliquer_garde_fous pour croiser une zone sensible déclarée avec la séance
# prévue. Cahier des charges ne fixe pas cette table : heuristique raisonnable,
# à affiner si besoin.
GROUPES_PAR_TYPE_SEANCE: dict[str, list[str]] = {
    "force": ["jambes", "dos", "épaules", "bras"],
    "explosivité_vitesse": ["jambes", "mollets"],
    "esthétique": ["bras", "épaules", "abdos", "dos", "jambes"],
    "endurance": ["jambes"],
    "décharge": [],
}


def calculer_phase_calendaire(
    date_aujourdhui: date,
    date_prochain_match: Optional[date],
    date_dernier_match: Optional[date],
) -> tuple[str, str]:
    """Détermine la phase calendaire et l'intensité max associée.

    Règles (telles que spécifiées) :
    - lendemain_match : jours écoulés depuis le dernier match == 0
    - veille_match : jours avant le prochain match == 1
    - approche_match : jours avant le prochain match == 2
    - phase_normale : sinon
    """
    if date_dernier_match is not None and (date_aujourdhui - date_dernier_match).days == 0:
        phase = "lendemain_match"
    elif date_prochain_match is not None and (date_prochain_match - date_aujourdhui).days == 1:
        phase = "veille_match"
    elif date_prochain_match is not None and (date_prochain_match - date_aujourdhui).days == 2:
        phase = "approche_match"
    else:
        phase = "phase_normale"

    return phase, PHASES_INTENSITE[phase]


def obtenir_priorites_poste(poste: str, sport: Optional[str] = "football") -> list[str]:
    """Priorités liées au poste, désormais dépendantes du sport pratiqué
    (voir user_model_v2.obtenir_priorites). `sport` par défaut à "football" pour ne
    pas casser un appelant qui ne le passe pas encore (compat descendante) ; les
    nouveaux appels (generer_recommandation) passent explicitement profil["contexte_sportif"]["sport"]."""
    return user_model_v2.obtenir_priorites(sport, poste)


def _rpe_liste(seances: list[dict[str, Any]]) -> str:
    return ", ".join(str(s.get("rpe")) if s.get("rpe") is not None else "?" for s in seances)


def _complete_liste(seances: list[dict[str, Any]]) -> str:
    return ", ".join(
        f"{s['pourcentage_complete']:.0f}%" if s.get("pourcentage_complete") is not None else "?"
        for s in seances
    )


def calculer_ajustement_charge(
    historique_3_dernieres_seances_meme_type: list[dict[str, Any]],
    niveau_physique_onboarding: Optional[str] = None,
    aujourdhui: Optional[date] = None,
) -> dict[str, Any]:
    """Calcule l'ajustement de charge/volume à partir des 3 dernières séances du même type.

    Chaque entrée d'historique attendue : {"date": date|str, "rpe": int|None,
    "pourcentage_complete": float|None}. Retourne
    {"charge_pct": float, "volume_pct": float, "raison": str}.

    Logique en cascade à décision unique (une seule règle s'applique, pas de cumul entre
    règles) : sécurité/reprise > décharge par accumulation > réduction liée au RPE de la
    dernière séance > réduction liée à la complétion de la dernière séance > progression sur
    plusieurs séances consécutives maîtrisées > signal positif isolé > maintien par défaut.
    """
    if not historique_3_dernieres_seances_meme_type:
        return {
            "charge_pct": 0.0,
            "volume_pct": 0.0,
            "raison": (
                "Aucun historique pour ce type de séance : on part du niveau déclaré à "
                f"l'onboarding ({niveau_physique_onboarding or 'non renseigné'})."
            ),
        }

    def _as_date(d: Any) -> date:
        return d if isinstance(d, date) else date.fromisoformat(d)

    seances = sorted(historique_3_dernieres_seances_meme_type, key=lambda s: _as_date(s["date"]), reverse=True)
    derniere = seances[0]
    rpe = derniere.get("rpe")
    pourcentage = derniere.get("pourcentage_complete")

    # 1. Sécurité / reprise après interruption : prioritaire sur toute progression ou décharge.
    jours_ecart = ((aujourdhui or date.today()) - _as_date(derniere["date"])).days
    if jours_ecart > 10:
        return {
            "charge_pct": -15.0,
            "volume_pct": 0.0,
            "raison": f"Dernière séance de ce type il y a {jours_ecart} jours : charge réduite par précaution pour une reprise en douceur.",
        }

    # 2. Décharge par accumulation : 3 dernières séances toutes dures ou incomplètes.
    if len(seances) >= 3:
        trois_dernieres = seances[:3]
        toutes_dures = all(
            (s.get("rpe") is not None and s["rpe"] >= 8)
            or (s.get("pourcentage_complete") is not None and s["pourcentage_complete"] < 70)
            for s in trois_dernieres
        )
        if toutes_dures:
            return {
                "charge_pct": -15.0,
                "volume_pct": -20.0,
                "raison": (
                    f"Les trois dernières séances de ce type ont été difficiles ou incomplètes "
                    f"(RPE {_rpe_liste(trois_dernieres)}, complétion {_complete_liste(trois_dernieres)}). "
                    "Semaine de décharge : charge et volume fortement réduits."
                ),
            }

    # 3. Réduction liée au RPE de la dernière séance.
    if rpe is not None and rpe >= 9:
        return {
            "charge_pct": -10.0,
            "volume_pct": -12.0,
            "raison": f"La dernière séance a été très difficile (RPE {rpe}). Je réduis nettement la charge pour favoriser la récupération.",
        }

    if rpe is not None and rpe == 8:
        return {
            "charge_pct": -5.0,
            "volume_pct": -5.0,
            "raison": "La dernière séance a été difficile (RPE 8). Je réduis légèrement la charge.",
        }

    # 4. Réduction liée à la complétion de la dernière séance (bloque toute progression).
    if pourcentage is not None and pourcentage < 70:
        return {
            "charge_pct": -5.0,
            "volume_pct": -10.0,
            "raison": f"La dernière séance n'a été complétée qu'à {pourcentage:.0f}%. Je réduis le volume plutôt que de progresser.",
        }

    # 5. Progression modérée : 3 dernières séances consécutives faciles et bien terminées.
    if len(seances) >= 3:
        trois_dernieres = seances[:3]
        toutes_faciles = all(
            s.get("rpe") is not None
            and s["rpe"] <= 5
            and s.get("pourcentage_complete") is not None
            and s["pourcentage_complete"] >= 90
            for s in trois_dernieres
        )
        if toutes_faciles:
            return {
                "charge_pct": 8.0,
                "volume_pct": 5.0,
                "raison": (
                    f"Les trois dernières séances de ce type ont été maîtrisées avec facilité "
                    f"(RPE {_rpe_liste(trois_dernieres)}, complétion {_complete_liste(trois_dernieres)}). "
                    "Je fais progresser charge et volume."
                ),
            }

    # 6. Progression légère : 2 dernières séances consécutives maîtrisées.
    if len(seances) >= 2:
        deux_dernieres = seances[:2]
        deux_dernieres_maitrisees = all(
            s.get("rpe") is not None
            and s["rpe"] <= 6
            and s.get("pourcentage_complete") is not None
            and s["pourcentage_complete"] >= 90
            for s in deux_dernieres
        )
        if deux_dernieres_maitrisees:
            return {
                "charge_pct": 5.0,
                "volume_pct": 0.0,
                "raison": (
                    f"Les deux dernières séances de ce type ont été maîtrisées "
                    f"(RPE {_rpe_liste(deux_dernieres)}, complétion {_complete_liste(deux_dernieres)}). "
                    "J'augmente légèrement la charge."
                ),
            }

    # 7. Signal positif isolé (une séance facile et bien terminée, mais pas encore de preuve
    # suffisante pour progresser).
    if rpe is not None and 4 <= rpe <= 5 and pourcentage is not None and pourcentage >= 90:
        return {
            "charge_pct": 0.0,
            "volume_pct": 0.0,
            "raison": (
                f"La dernière séance a été facile et bien terminée (RPE {rpe}, complétion {pourcentage:.0f}%). "
                "C'est un bon signal, mais j'attends une confirmation avant d'augmenter la charge."
            ),
        }

    # 8. Maintien par défaut.
    return {"charge_pct": 0.0, "volume_pct": 0.0, "raison": "Pas de signal fort dans l'historique récent : charge et volume inchangés."}


def appliquer_garde_fous(
    recommandation: dict[str, Any],
    zones_sensibles: list[str],
    entrainements_club_semaine: int,
    seance_prevue_meme_jour_club: bool,
    historique_recent: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    """Applique les garde-fous de sécurité/charge et retourne (recommandation_ajustee, raisons).

    La recommandation ajustée porte une clé "exclusions" (zones à exclure) et peut
    voir son "type_seance_suggere" / "intensite_max" / "ajustement_volume_pct" modifiés.
    """
    reco = dict(recommandation)
    raisons: list[str] = []
    exclusions: list[str] = []

    groupes_seance = GROUPES_PAR_TYPE_SEANCE.get(reco.get("type_seance_suggere", ""), [])
    groupes_seance_lower = {g.lower() for g in groupes_seance}
    for zone in zones_sensibles:
        if zone.lower() in groupes_seance_lower:
            exclusions.append(zone)
            raisons.append(f"Zone sensible déclarée « {zone} » exclue de la séance (groupe musculaire concerné par le type de séance prévu).")

    if entrainements_club_semaine >= 2 and seance_prevue_meme_jour_club:
        reco["ajustement_volume_pct"] = reco.get("ajustement_volume_pct", 0.0) - 30.0
        raisons.append("2 entraînements club ou plus cette semaine, dont un le même jour : volume réduit de 30%, priorité à la qualité sur le volume.")

    def _as_date(d: Any) -> date:
        return d if isinstance(d, date) else date.fromisoformat(d)

    trois_dernieres = sorted(historique_recent, key=lambda s: _as_date(s["date"]), reverse=True)[:3]
    seances_dures_ou_ratees = [
        s
        for s in trois_dernieres
        if (s.get("pourcentage_complete") is not None and s["pourcentage_complete"] < 70)
        or (s.get("rpe") is not None and s["rpe"] >= 8)
    ]
    if len(trois_dernieres) == 3 and len(seances_dures_ou_ratees) == 3:
        reco["type_seance_suggere"] = "décharge"
        reco["intensite_max"] = "récupération"
        reco["ajustement_volume_pct"] = -30.0
        raisons.append(
            "3 dernières séances consécutives ratées (< 70% complétées) ou très dures (RPE ≥ 8) : "
            "mode semaine de décharge activé, volume -30% sur tout, indépendamment du calendrier."
        )

    reco["exclusions"] = exclusions
    return reco, raisons


def _dates_matchs_proches(calendrier: Optional[dict[str, Any]], aujourdhui: date, fenetre_jours: int = 21) -> tuple[Optional[date], Optional[date]]:
    """Dérive (date_prochain_match, date_dernier_match) depuis calendrier_matchs du profil
    (jour_habituel + exceptions), en cherchant dans une fenêtre de +/- fenetre_jours jours."""
    if not calendrier:
        return None, None

    dates: set[date] = set()

    for exception in calendrier.get("exceptions") or []:
        d = exception.get("date")
        if d:
            dates.add(d if isinstance(d, date) else date.fromisoformat(d))

    jour_habituel = calendrier.get("jour_habituel")
    if jour_habituel and jour_habituel in JOURS_SEMAINE:
        cible = JOURS_SEMAINE.index(jour_habituel)
        for offset in range(-fenetre_jours, fenetre_jours + 1):
            d = aujourdhui + timedelta(days=offset)
            if d.weekday() == cible:
                dates.add(d)

    prochains = sorted(d for d in dates if d >= aujourdhui)
    passes = sorted((d for d in dates if d < aujourdhui), reverse=True)

    return (prochains[0] if prochains else None), (passes[0] if passes else None)


def _suggerer_type_seance(
    phase: str,
    priorites: list[str],
    objectif_esthetique: Optional[dict[str, Any]],
    type_seance_gabarit: Optional[str] = None,
) -> str:
    """Choisit un type de séance parmi force / explosivité_vitesse / esthétique / endurance / décharge.

    Priorité (la plus haute d'abord) :
    1. Phase calendaire contraignante (lendemain/veille/approche de match) — l'emporte
       toujours, y compris sur ce que prévoit le gabarit hebdomadaire d'un programme actif.
    2. type_seance_gabarit : ce que prévoit le gabarit hebdomadaire du programme actif pour
       aujourd'hui, s'il y en a un (remplace l'ancienne heuristique par défaut).
    3. À défaut de programme actif, heuristique de repli : objectif esthétique déclaré,
       sinon force par défaut. Le cahier des charges ne fixe pas cette dernière règle à la
       lettre — elle ne sert que de filet de sécurité quand aucun programme n'encadre la séance.
    """
    if phase == "lendemain_match":
        return "décharge"
    if phase in ("veille_match", "approche_match"):
        return "explosivité_vitesse"
    if type_seance_gabarit:
        return type_seance_gabarit
    if objectif_esthetique and (objectif_esthetique.get("tags") or objectif_esthetique.get("texte_libre")):
        return "esthétique"
    return "force"


def generer_recommandation(
    profil: dict[str, Any],
    historique: dict[str, Any],
    etat_du_jour: dict[str, Any],
    type_seance_gabarit: Optional[str] = None,
    aujourdhui: Optional[date] = None,
) -> dict[str, Any]:
    """Fonction principale : combine les règles ci-dessus en une recommandation structurée.

    profil : dict tel que renvoyé par ProfilOut (poste, niveau_physique,
        niveaux_qualites_physiques, calendrier_matchs, objectif_esthetique, ...).
    historique : {
        "par_type": {type_seance: [{"date", "rpe", "pourcentage_complete"}, ...]},  # 3 dernières par type
        "recent": [{"date", "rpe", "pourcentage_complete"}, ...],  # 3 dernières séances toutes confondues
        "zones_sensibles_recentes": [str, ...],
    }
    etat_du_jour : {"sommeil", "motivation", "temps_dispo", "envie_texte", "entrainement_club_semaine"}
    type_seance_gabarit : type de séance prévu aujourd'hui par le gabarit hebdomadaire du
        programme actif, s'il y en a un (voir main.py::generer_seance) — cadre la séance,
        mais reste subordonné à la phase calendaire (cf. _suggerer_type_seance).
    """
    aujourdhui = aujourdhui or date.today()
    date_prochain_match, date_dernier_match = _dates_matchs_proches(profil.get("calendrier_matchs"), aujourdhui)

    phase, intensite_max = calculer_phase_calendaire(aujourdhui, date_prochain_match, date_dernier_match)
    sport = (profil.get("contexte_sportif") or {}).get("sport")
    priorites = obtenir_priorites_poste(profil.get("poste", ""), sport=sport)
    type_seance_suggere = _suggerer_type_seance(phase, priorites, profil.get("objectif_esthetique"), type_seance_gabarit)

    historique_meme_type = (historique.get("par_type") or {}).get(type_seance_suggere, [])
    ajustement = calculer_ajustement_charge(historique_meme_type, profil.get("niveau_physique"), aujourdhui)

    recommandation: dict[str, Any] = {
        "phase_calendaire": phase,
        "intensite_max": intensite_max,
        "priorites_poste": priorites,
        "type_seance_suggere": type_seance_suggere,
        "ajustement_charge_pct": ajustement["charge_pct"],
        "ajustement_volume_pct": ajustement["volume_pct"],
        "raisons": [ajustement["raison"]],
    }

    # "2_fois_ou_plus" / "1_fois" / "non" -> nombre d'entraînements club déclarés cette semaine.
    club_semaine_brut = etat_du_jour.get("entrainement_club_semaine")
    entrainements_club_semaine = {"non": 0, "1_fois": 1, "2_fois_ou_plus": 2}.get(club_semaine_brut, 0)
    # Pas de signal explicite "entraînement club aujourd'hui" dans le formulaire :
    # on suppose prudemment une coïncidence possible dès que 2 entraînements club ou
    # plus sont déclarés sur la semaine (heuristique, à affiner si le formulaire évolue).
    seance_prevue_meme_jour_club = entrainements_club_semaine >= 2

    recommandation, raisons_garde_fous = appliquer_garde_fous(
        recommandation,
        historique.get("zones_sensibles_recentes") or [],
        entrainements_club_semaine,
        seance_prevue_meme_jour_club,
        historique.get("recent") or [],
    )
    recommandation["raisons"].extend(raisons_garde_fous)

    return recommandation
