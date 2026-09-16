from datetime import date, timedelta
from typing import Optional

JOURS_SEMAINE = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]


def _normaliser_dates(valeurs) -> set[str]:
    """Dates d'un calendrier ramenées à des chaînes ISO, qu'elles soient déjà des `date`
    (profil en mémoire) ou des `str` (colonne JSON relue depuis la base)."""
    normalisees = set()
    for valeur in valeurs or []:
        if isinstance(valeur, date):
            normalisees.add(valeur.isoformat())
        elif valeur:
            normalisees.add(str(valeur))
    return normalisees


def _is_match_date(d: date, calendrier: Optional[dict]) -> bool:
    if not calendrier:
        return False

    # Match annulé/déplacé : prioritaire sur tout le reste, y compris une exception qui aurait
    # ajouté cette même date (voir schemas.CalendrierMatchs.annulations et la logique jumelle
    # de regles_seance._dates_matchs_proches).
    if d.isoformat() in _normaliser_dates(calendrier.get("annulations")):
        return False

    exceptions = calendrier.get("exceptions") or []
    exception_dates = _normaliser_dates(e.get("date") for e in exceptions)
    if d.isoformat() in exception_dates:
        return True

    jour_habituel = calendrier.get("jour_habituel")
    if jour_habituel and JOURS_SEMAINE[d.weekday()] == jour_habituel:
        return True

    return False


def compute_phase(d: date, calendrier: Optional[dict]) -> str:
    """Détermine la phase calendaire d'une séance à partir du calendrier de matchs du profil.

    - jour_de_match : d correspond au jour habituel ou à une exception
    - veille_de_match : un match a lieu le lendemain
    - lendemain_de_match : un match a eu lieu la veille
    - developpement : aucun match à proximité
    """
    if _is_match_date(d, calendrier):
        return "jour_de_match"
    if _is_match_date(d + timedelta(days=1), calendrier):
        return "veille_de_match"
    if _is_match_date(d - timedelta(days=1), calendrier):
        return "lendemain_de_match"
    return "developpement"
