"""Bilan hebdomadaire — agrégation déterministe de ce qui a RÉELLEMENT été réalisé.

Module volontairement pur (aucun import SQLAlchemy, aucune dépendance FastAPI) : il reçoit des
listes de dicts déjà extraites de la base par main.py et rend le bilan. Ça le rend testable sans
base de données, et ça garantit qu'aucune métrique n'est inventée ici — chaque chiffre sorti
provient d'une série réellement loguée ou d'une séance réellement terminée.

Règle de conception : si la donnée n'existe pas, le champ vaut None / la liste est vide. On ne
remplit jamais un écran avec une valeur de remplissage (cf. exigence produit « ne fabrique jamais
de métrique artificielle »).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterable, Optional

# En dessous de ce seuil (en %), une variation de charge est considérée comme du bruit de
# mesure/arrondi plutôt qu'une vraie progression : l'exercice est classé en stagnation.
SEUIL_PROGRESSION_PCT = 2.0

# Nombre maximum d'exercices listés dans chaque rubrique du bilan — le bilan doit rester court
# et lisible, pas exhaustif.
MAX_EXERCICES_LISTES = 3


def _fenetre(debut: date, fin: date, valeur: date) -> bool:
    return debut <= valeur <= fin


def _volume_serie(serie: dict) -> float:
    """Volume (kg soulevés) d'une série cochée : poids × répétitions.

    Une série au poids du corps (poids_kg à None ou 0) ne contribue pas au volume en kg — on ne
    lui invente pas une charge équivalente au poids de corps, qui serait une métrique fabriquée.
    """
    poids = serie.get("poids_kg")
    reps = serie.get("repetitions")
    if not poids or not reps:
        return 0.0
    return float(poids) * float(reps)


def _series_cochees(series: Iterable[dict], debut: date, fin: date) -> list[dict]:
    retenues = []
    for serie in series:
        if not serie.get("coche"):
            continue
        serie_date = serie.get("date")
        if serie_date is None or not _fenetre(debut, fin, serie_date):
            continue
        retenues.append(serie)
    return retenues


def _charge_max_par_exercice(series: Iterable[dict]) -> dict[str, float]:
    """Charge maximale validée par exercice (clé : nom d'exercice)."""
    maxima: dict[str, float] = {}
    for serie in series:
        poids = serie.get("poids_kg")
        nom = serie.get("nom_exercice")
        if not poids or not nom:
            continue
        maxima[nom] = max(maxima.get(nom, 0.0), float(poids))
    return maxima


def _variation_pct(avant: float, apres: float) -> Optional[float]:
    if not avant:
        return None
    return round((apres - avant) / avant * 100, 1)


def _moyenne(valeurs: list[float]) -> Optional[float]:
    if not valeurs:
        return None
    return round(sum(valeurs) / len(valeurs), 1)


def construire_bilan(
    seances: list[dict],
    series: list[dict],
    aujourdhui: date,
    jours: int = 7,
) -> dict[str, Any]:
    """Construit le bilan de la fenêtre [aujourdhui - jours + 1, aujourdhui].

    seances : [{"date": date, "rpe": int|None, "pourcentage_complete": float|None,
                "type_seance": str|None}] — uniquement des séances TERMINÉES.
    series  : [{"date": date, "nom_exercice": str, "poids_kg": float|None,
                "repetitions": int|None, "coche": bool}] — séries loguées, toutes fenêtres
              confondues (le filtrage temporel est fait ici).
    """
    fin = aujourdhui
    debut = aujourdhui - timedelta(days=jours - 1)
    fin_prec = debut - timedelta(days=1)
    debut_prec = fin_prec - timedelta(days=jours - 1)

    seances_periode = [s for s in seances if s.get("date") and _fenetre(debut, fin, s["date"])]
    seances_prec = [s for s in seances if s.get("date") and _fenetre(debut_prec, fin_prec, s["date"])]

    series_periode = _series_cochees(series, debut, fin)
    series_prec = _series_cochees(series, debut_prec, fin_prec)

    volume = round(sum(_volume_serie(s) for s in series_periode), 1)
    volume_prec = round(sum(_volume_serie(s) for s in series_prec), 1)

    maxima = _charge_max_par_exercice(series_periode)
    maxima_prec = _charge_max_par_exercice(series_prec)

    progressions = []
    stagnations = []
    for nom, charge in sorted(maxima.items()):
        charge_prec = maxima_prec.get(nom)
        if charge_prec is None:
            continue  # pas de point de comparaison : on ne conclut rien
        variation = _variation_pct(charge_prec, charge)
        if variation is None:
            continue
        if variation > SEUIL_PROGRESSION_PCT:
            progressions.append(
                {
                    "exercice": nom,
                    "charge_precedente_kg": charge_prec,
                    "charge_kg": charge,
                    "variation_pct": variation,
                }
            )
        elif abs(variation) <= SEUIL_PROGRESSION_PCT:
            stagnations.append({"exercice": nom, "charge_kg": charge})

    progressions.sort(key=lambda p: p["variation_pct"], reverse=True)

    jours_actifs = len({s["date"] for s in seances_periode})
    rpe_moyen = _moyenne([float(s["rpe"]) for s in seances_periode if s.get("rpe") is not None])
    completion = _moyenne(
        [float(s["pourcentage_complete"]) for s in seances_periode if s.get("pourcentage_complete") is not None]
    )

    return {
        "periode_debut": debut.isoformat(),
        "periode_fin": fin.isoformat(),
        "seances_realisees": len(seances_periode),
        "seances_realisees_precedent": len(seances_prec),
        "jours_actifs": jours_actifs,
        "jours_fenetre": jours,
        "volume_kg": volume,
        "volume_kg_precedent": volume_prec,
        "volume_variation_pct": _variation_pct(volume_prec, volume) if volume_prec else None,
        "rpe_moyen": rpe_moyen,
        "completion_moyenne": completion,
        "progressions": progressions[:MAX_EXERCICES_LISTES],
        "stagnations": stagnations[:MAX_EXERCICES_LISTES],
        "points": _formuler_points(
            len(seances_periode),
            len(seances_prec),
            volume,
            volume_prec,
            progressions,
            stagnations,
            rpe_moyen,
            completion,
        ),
    }


def _formuler_points(
    n_seances: int,
    n_seances_prec: int,
    volume: float,
    volume_prec: float,
    progressions: list[dict],
    stagnations: list[dict],
    rpe_moyen: Optional[float],
    completion: Optional[float],
) -> list[str]:
    """Deux à quatre phrases courtes, chacune adossée à un chiffre réel de la période.

    Aucune phrase n'est produite si la donnée correspondante manque : un bilan sans séance dit
    simplement qu'il n'y a rien à analyser, plutôt que d'habiller du vide.
    """
    if n_seances == 0:
        return ["Aucune séance terminée sur la période : rien à analyser cette semaine."]

    points: list[str] = []

    if n_seances_prec:
        delta = n_seances - n_seances_prec
        if delta > 0:
            points.append(f"{n_seances} séances terminées, soit {delta} de plus que la semaine précédente.")
        elif delta < 0:
            points.append(f"{n_seances} séances terminées, soit {abs(delta)} de moins que la semaine précédente.")
        else:
            points.append(f"{n_seances} séances terminées, même rythme que la semaine précédente.")
    else:
        points.append(f"{n_seances} séance{'s' if n_seances > 1 else ''} terminée{'s' if n_seances > 1 else ''}.")

    if volume and volume_prec:
        variation = _variation_pct(volume_prec, volume)
        if variation is not None and abs(variation) > SEUIL_PROGRESSION_PCT:
            sens = "en hausse" if variation > 0 else "en baisse"
            points.append(f"Volume total {sens} de {abs(variation):.0f} % ({volume:.0f} kg soulevés).")
        else:
            points.append(f"Volume total stable ({volume:.0f} kg soulevés).")
    elif volume:
        points.append(f"{volume:.0f} kg soulevés au total.")

    if progressions:
        meilleur = progressions[0]
        points.append(
            f"Charge en progression sur {meilleur['exercice']} : "
            f"{meilleur['charge_precedente_kg']:.0f} → {meilleur['charge_kg']:.0f} kg."
        )
    elif stagnations:
        points.append(
            f"Charge stable sur {stagnations[0]['exercice']} ({stagnations[0]['charge_kg']:.0f} kg) : "
            "c'est le point à débloquer."
        )

    if completion is not None and completion < 80:
        points.append(f"Séances complétées à {completion:.0f} % en moyenne : des séries restent non validées.")
    elif rpe_moyen is not None:
        points.append(f"RPE moyen de {rpe_moyen} sur la période.")

    return points[:4]
