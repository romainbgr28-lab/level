"""Contexte déterministe du jour : ce que LEVEL a décidé pour aujourd'hui, et pourquoi.

Une seule fonction pure (aucune I/O, aucun appel Mistral), consommée par
``GET /api/jour/contexte`` (main.py) et testée sans base ni FastAPI
(test_contexte_jour.py).

Elle existe pour que l'écran Aujourd'hui n'ait plus à redériver côté frontend des
décisions qui appartiennent au moteur : jour de match, jour indisponible, jour de repos
programmé, type de séance prévu, position dans la semaine et prochaine séance. Le
frontend affiche le statut renvoyé ici, il n'en recalcule aucun.

Conventions de jours (à ne jamais mélanger) :
- ``gabarit_hebdomadaire`` et ``jour_abbrev`` : abrégé capitalisé "Lun".."Dim"
  (regles_seance.JOURS_SEMAINE_ABBREV) ;
- ``Profil.disponibilites`` : jour complet minuscule "lundi".."dimanche"
  (user_model_v2.JOURS_DISPONIBILITES) ;
- ``calendrier_matchs.jour_habituel`` : jour complet capitalisé "Lundi".."Dimanche"
  (regles_seance.JOURS_SEMAINE).
"""

from datetime import date, timedelta
from typing import Any, Optional

import moteur_decision
import regles_seance
import user_model_v2

# Statuts possibles du jour, du plus contraignant au plus permissif. Toute valeur ajoutée ici
# doit être gérée explicitement par src/screens/Today.tsx (pas de branche "par défaut" muette).
STATUTS_JOUR = ("aucun_profil", "aucun_programme", "match", "repos", "indisponible", "seance")

_JOURS_LABEL = {
    "Lun": "Lundi", "Mar": "Mardi", "Mer": "Mercredi", "Jeu": "Jeudi",
    "Ven": "Vendredi", "Sam": "Samedi", "Dim": "Dimanche",
}


def _jour_abbrev(d: date) -> str:
    return regles_seance.JOURS_SEMAINE_ABBREV[d.weekday()]


def _jour_complet_lower(d: date) -> str:
    return user_model_v2.JOURS_DISPONIBILITES[d.weekday()]


def _est_jour_de_match(calendrier: Optional[dict[str, Any]], jour: date) -> bool:
    prochain, _ = regles_seance._dates_matchs_proches(calendrier, jour)
    return prochain == jour


def _statut_pour_jour(
    jour: date,
    gabarit: dict[str, Any],
    disponibilites: dict[str, Any],
    calendrier: Optional[dict[str, Any]],
) -> tuple[str, Optional[str]]:
    """(statut, type_seance_prevu) pour un jour donné. Le jour de match prime sur tout le
    reste : c'est une contrainte absolue du calendrier sportif, jamais un choix de gabarit."""
    if _est_jour_de_match(calendrier, jour):
        return "match", None

    type_brut = gabarit.get(_jour_abbrev(jour))
    type_prevu = moteur_decision.normaliser_type_seance_programme(type_brut)
    if type_prevu == "repos":
        return "repos", "repos"
    if type_prevu:
        return "seance", type_prevu

    # Aucun type au gabarit : soit le jour n'est pas déclaré disponible (contrainte du profil),
    # soit le programme n'a simplement rien placé ce jour-là (repos de fait).
    if disponibilites.get(_jour_complet_lower(jour)) is None:
        return "indisponible", None
    return "repos", None


def construire_contexte_jour(
    profil: Optional[dict[str, Any]],
    programme: Optional[dict[str, Any]],
    aujourdhui: date,
    seance_du_jour: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Contexte complet du jour pour l'écran Aujourd'hui.

    `programme` : dict {gabarit_hebdomadaire, phases, duree_semaines, date_debut} du programme
    actif, ou None. `seance_du_jour` : {id, statut, nom} de la séance déjà en base, ou None.
    """
    jour_abbrev = _jour_abbrev(aujourdhui)
    base: dict[str, Any] = {
        "date": aujourdhui,
        "jour_abbrev": jour_abbrev,
        "jour_label": _JOURS_LABEL[jour_abbrev],
        "statut": "aucun_profil",
        "type_seance_prevu": None,
        "phase_calendaire": "phase_normale",
        "semaine_programme": None,
        "duree_semaines": None,
        "phase_nom": None,
        "phase_description": None,
        "seance_id": None,
        "seance_statut": None,
        "seance_nom": None,
        "prochaine_seance": None,
        "semaine": [],
    }

    if seance_du_jour:
        base["seance_id"] = seance_du_jour.get("id")
        base["seance_statut"] = seance_du_jour.get("statut")
        base["seance_nom"] = seance_du_jour.get("nom")

    if profil is None:
        return base

    calendrier = profil.get("calendrier_matchs") or {}
    disponibilites = profil.get("disponibilites") or {}

    prochain, dernier = regles_seance._dates_matchs_proches(calendrier, aujourdhui)
    base["phase_calendaire"], _ = regles_seance.calculer_phase_calendaire(aujourdhui, prochain, dernier)

    if programme is None:
        base["statut"] = "match" if base["phase_calendaire"] == "jour_match" else "aucun_programme"
        return base

    gabarit = programme.get("gabarit_hebdomadaire") or {}
    duree_semaines = programme.get("duree_semaines") or moteur_decision.DUREE_SEMAINES_PROGRAMME_DEFAUT
    base["duree_semaines"] = duree_semaines

    date_debut = programme.get("date_debut")
    if isinstance(date_debut, str):
        date_debut = date.fromisoformat(date_debut)
    if isinstance(date_debut, date):
        semaine = (aujourdhui - date_debut).days // 7 + 1
        base["semaine_programme"] = min(max(semaine, 1), duree_semaines)

    for phase in programme.get("phases") or []:
        if not isinstance(phase, dict):
            continue
        debut, fin = phase.get("semaine_debut"), phase.get("semaine_fin")
        semaine = base["semaine_programme"]
        if semaine is not None and isinstance(debut, int) and isinstance(fin, int) and debut <= semaine <= fin:
            base["phase_nom"] = phase.get("nom")
            base["phase_description"] = phase.get("description")
            break

    statut, type_prevu = _statut_pour_jour(aujourdhui, gabarit, disponibilites, calendrier)
    base["statut"] = statut
    base["type_seance_prevu"] = type_prevu

    # Vue de la semaine en cours (lundi -> dimanche), même logique de statut appliquée à chaque
    # jour : l'utilisateur voit où il en est et ce qui arrive, sans recalcul côté frontend.
    lundi = aujourdhui - timedelta(days=aujourdhui.weekday())
    for offset in range(7):
        jour = lundi + timedelta(days=offset)
        statut_jour, type_jour = _statut_pour_jour(jour, gabarit, disponibilites, calendrier)
        base["semaine"].append({
            "date": jour,
            "jour_abbrev": _jour_abbrev(jour),
            "jour_label": _JOURS_LABEL[_jour_abbrev(jour)],
            "statut": statut_jour,
            "type_seance_prevu": type_jour,
            "est_aujourdhui": jour == aujourdhui,
            "est_passe": jour < aujourdhui,
        })

    # Prochaine séance réellement prévue dans les 7 jours qui suivent (jamais aujourd'hui) :
    # sert aux états "repos", "match" et "séance terminée" pour toujours répondre à
    # « et ensuite ? » plutôt que laisser l'écran sans suite.
    for offset in range(1, 8):
        jour = aujourdhui + timedelta(days=offset)
        statut_jour, type_jour = _statut_pour_jour(jour, gabarit, disponibilites, calendrier)
        if statut_jour == "seance" and type_jour:
            base["prochaine_seance"] = {
                "date": jour,
                "jour_abbrev": _jour_abbrev(jour),
                "jour_label": _JOURS_LABEL[_jour_abbrev(jour)],
                "type_seance_prevu": type_jour,
            }
            break

    return base
