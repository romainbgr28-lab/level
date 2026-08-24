from datetime import date, timedelta
from typing import Optional

JOURS_SEMAINE = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]


def _is_match_date(d: date, calendrier: Optional[dict]) -> bool:
    if not calendrier:
        return False

    exceptions = calendrier.get("exceptions") or []
    exception_dates = {e["date"] for e in exceptions if e.get("date")}
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
