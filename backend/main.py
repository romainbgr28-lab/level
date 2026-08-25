import logging
import os
import re
from datetime import date, timedelta
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func
from sqlalchemy.orm import Session

import connaissances
import duree_seance
import mistral_client
import models
import regles_seance
import schemas
from dev_date import get_current_date
from charge_depart import estimer_charge_depart, formater_recommandation_charge
from calendrier import compute_phase
from database import SessionLocal, get_db
from migrate import migrer
from seed import seed

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("level")

migrer()  # crée les tables manquantes + ajoute les colonnes additives manquantes

with SessionLocal() as _db:
    seed(_db)

app = FastAPI(title="LEVEL API")

# CORS_ORIGINS: liste d'origines séparées par des virgules (ex: https://level.vercel.app).
# Sans variable définie, on autorise tout (pratique en local / avant configuration).
_cors_origins_env = os.environ.get("CORS_ORIGINS")
allow_origins = [o.strip() for o in _cors_origins_env.split(",")] if _cors_origins_env else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Profil ----------

@app.get("/api/profil", response_model=Optional[schemas.ProfilOut])
def get_profil(db: Session = Depends(get_db)):
    return db.query(models.Profil).order_by(models.Profil.id.desc()).first()


@app.post("/api/profil", response_model=schemas.ProfilOut)
def upsert_profil(payload: schemas.ProfilCreate, db: Session = Depends(get_db)):
    # mode="json" : les dates imbriquées dans calendrier_matchs.exceptions doivent être
    # sérialisées en str avant stockage dans une colonne JSON (sqlite ne sait pas encoder `date`).
    data = payload.model_dump(mode="json")
    existing = db.query(models.Profil).order_by(models.Profil.id.desc()).first()
    if existing:
        for key, value in data.items():
            setattr(existing, key, value)
        db.commit()
        db.refresh(existing)
        return existing
    profil = models.Profil(**data)
    db.add(profil)
    db.commit()
    db.refresh(profil)
    return profil


@app.delete("/api/profil", status_code=204)
def delete_profil(db: Session = Depends(get_db)):
    """Supprime le(s) profil(s) enregistré(s) pour forcer un nouvel onboarding.

    Endpoint temporaire, exposé via un bouton de reset dans l'écran Profil,
    tant qu'il n'existe pas de vrai flux d'édition de profil.
    """
    db.query(models.Profil).delete()
    db.commit()
    return None


# ---------- Seances ----------

@app.get("/api/seances", response_model=list[schemas.SeanceOut])
def list_seances(db: Session = Depends(get_db)):
    return db.query(models.Seance).order_by(models.Seance.date.desc()).all()


@app.get("/api/seances/today", response_model=Optional[schemas.SeanceOut])
def get_today_seance(db: Session = Depends(get_db), today: date = Depends(get_current_date)):
    return db.query(models.Seance).filter(models.Seance.date == today).first()


@app.delete("/api/seances/today", status_code=204)
def delete_today_seance(db: Session = Depends(get_db), today: date = Depends(get_current_date)):
    """Supprime la/les séance(s) du jour pour forcer une nouvelle génération.

    Endpoint temporaire, exposé via un bouton de reset côté écran Aujourd'hui,
    utile notamment pour effacer une séance restée en base d'avant le passage
    au flux 100% généré par /api/seance/generer.
    """
    db.query(models.Seance).filter(models.Seance.date == today).delete()
    db.commit()
    return None


@app.get("/api/seances/{seance_id}", response_model=schemas.SeanceOut)
def get_seance(seance_id: int, db: Session = Depends(get_db)):
    seance = db.get(models.Seance, seance_id)
    if not seance:
        raise HTTPException(status_code=404, detail="Séance introuvable")
    return seance


@app.post("/api/seances", response_model=schemas.SeanceOut)
def create_seance(payload: schemas.SeanceCreate, db: Session = Depends(get_db)):
    seance = models.Seance(**payload.model_dump())
    db.add(seance)
    db.commit()
    db.refresh(seance)
    return seance


@app.patch("/api/seances/{seance_id}", response_model=schemas.SeanceOut)
def update_seance(seance_id: int, payload: schemas.SeanceUpdate, db: Session = Depends(get_db)):
    seance = db.get(models.Seance, seance_id)
    if not seance:
        raise HTTPException(status_code=404, detail="Séance introuvable")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(seance, key, value)
    db.commit()
    db.refresh(seance)

    if seance.statut == "terminee":
        today_streak = db.get(models.Streak, seance.date)
        if not today_streak:
            today_streak = models.Streak(date=seance.date, sport_fait=1, apprentissage_fait=0)
            db.add(today_streak)
        else:
            today_streak.sport_fait = 1
        db.commit()

    return seance


# ---------- Bibliothèque d'exercices ----------

@app.get("/api/exercices_bibliotheque", response_model=list[schemas.ExerciceBibliothequeOut])
def list_exercices_bibliotheque(db: Session = Depends(get_db)):
    return db.query(models.ExerciceBibliotheque).order_by(models.ExerciceBibliotheque.nom.asc()).all()


@app.get("/api/exercices_bibliotheque/{exercice_id}", response_model=schemas.ExerciceBibliothequeOut)
def get_exercice_bibliotheque(exercice_id: int, db: Session = Depends(get_db)):
    exercice = db.get(models.ExerciceBibliotheque, exercice_id)
    if not exercice:
        raise HTTPException(status_code=404, detail="Exercice introuvable")
    return exercice


@app.post("/api/exercices_bibliotheque", response_model=schemas.ExerciceBibliothequeOut)
def create_exercice_bibliotheque(payload: schemas.ExerciceBibliothequeCreate, db: Session = Depends(get_db)):
    exercice = models.ExerciceBibliotheque(**payload.model_dump())
    db.add(exercice)
    db.commit()
    db.refresh(exercice)
    return exercice


@app.get("/api/exercices_bibliotheque/{exercice_id}/derniere_performance", response_model=schemas.DernierePerformanceOut)
def get_derniere_performance(exercice_id: int, seance_id: Optional[int] = None, db: Session = Depends(get_db)):
    """« Précédent » façon Hevy : les séries cochées de la dernière séance (autre que
    `seance_id`, la séance en cours) où cet exercice a été loggé."""
    query = db.query(models.SerieLoggee).filter(
        models.SerieLoggee.exercice_id == exercice_id,
        models.SerieLoggee.coche == 1,
    )
    if seance_id is not None:
        query = query.filter(models.SerieLoggee.seance_id != seance_id)

    derniere_seance_id = (
        query.join(models.Seance, models.Seance.id == models.SerieLoggee.seance_id)
        .order_by(models.Seance.date.desc(), models.SerieLoggee.horodatage.desc())
        .with_entities(models.SerieLoggee.seance_id)
        .first()
    )
    if not derniere_seance_id:
        return schemas.DernierePerformanceOut(date=None, series=[])

    derniere_seance_id = derniere_seance_id[0]
    seance = db.get(models.Seance, derniere_seance_id)
    series = (
        db.query(models.SerieLoggee)
        .filter(
            models.SerieLoggee.exercice_id == exercice_id,
            models.SerieLoggee.seance_id == derniere_seance_id,
            models.SerieLoggee.coche == 1,
        )
        .order_by(models.SerieLoggee.numero_serie.asc())
        .all()
    )
    return schemas.DernierePerformanceOut(date=seance.date if seance else None, series=series)


# ---------- Séries loguées (logging temps réel façon Hevy) ----------

# Validation rapide par bouton (facile / comme prévu / dur) -> RPE approximatif stocké
# dans series_loggees.rpe_approx, utilisé par le moteur de règles pour la charge de la
# prochaine séance du même type (voir regles_seance.calculer_ajustement_charge : rpe >= 8
# réduit charge/volume, rpe <= 6 sur 2 séances maîtrisées l'augmente).
DIFFICULTE_RPE_APPROX = {"facile": 5, "comme_prevu": 7, "dur": 9}


def _rpe_approx_depuis_difficulte(difficulte: Optional[str]) -> Optional[int]:
    return DIFFICULTE_RPE_APPROX.get(difficulte) if difficulte else None


# Extraction du "prévu" (reps/charge) depuis les champs texte libres de Seance.exercices
# (ex: repetitions="8-12", charge_indicative="20 kg" | "poids du corps" | "à ajuster selon
# ressenti"). Mêmes règles que repsCible/chargeCible côté frontend (Today.tsx) pour que la
# cible affichée à l'utilisateur et le "prévu" persisté en base soient toujours cohérents.
def _reps_prevues_depuis_repetitions(repetitions: Optional[str]) -> Optional[int]:
    if not repetitions:
        return None
    m = re.search(r"\d+", repetitions)
    return int(m.group()) if m else None


def _charge_prevue_depuis_indicative(charge_indicative: Optional[str]) -> Optional[float]:
    if not charge_indicative or re.search(r"corps", charge_indicative, re.IGNORECASE):
        return None
    m = re.search(r"\d+(?:[.,]\d+)?", charge_indicative)
    return float(m.group().replace(",", ".")) if m else None


def _prevu_pour_exercice(
    seance: Optional[models.Seance], exercice_id: int
) -> tuple[Optional[int], Optional[float]]:
    """Retrouve l'item de Seance.exercices correspondant à cet exercice (association par
    exercice_id, pas par position dans la liste : un exercice ne peut apparaître qu'une
    fois par séance, chaque item porte son propre exercice_id)."""
    if not seance:
        return None, None
    for item in seance.exercices or []:
        if item.get("exercice_id") == exercice_id:
            return (
                _reps_prevues_depuis_repetitions(item.get("repetitions")),
                _charge_prevue_depuis_indicative(item.get("charge_indicative")),
            )
    return None, None


@app.get("/api/series_loggees", response_model=list[schemas.SerieLoggeeOut])
def list_series_loggees(seance_id: int, db: Session = Depends(get_db)):
    return (
        db.query(models.SerieLoggee)
        .filter(models.SerieLoggee.seance_id == seance_id)
        .order_by(models.SerieLoggee.exercice_id.asc(), models.SerieLoggee.numero_serie.asc())
        .all()
    )


@app.post("/api/series_loggees", response_model=schemas.SerieLoggeeOut)
def create_serie_loggee(payload: schemas.SerieLoggeeCreate, db: Session = Depends(get_db)):
    data = payload.model_dump()
    data["coche"] = int(data["coche"])
    if data.get("rpe_approx") is None:
        data["rpe_approx"] = _rpe_approx_depuis_difficulte(data.get("difficulte"))

    # Le prévu (reps/charge) n'est jamais envoyé par le client : il est retrouvé côté
    # serveur depuis la séance concernée, identique pour le tap rapide et la saisie
    # manuelle puisque les deux passent par ce même endpoint avec le même payload.
    seance = db.get(models.Seance, data["seance_id"])
    reps_prevues, charge_prevue_kg = _prevu_pour_exercice(seance, data["exercice_id"])

    serie = models.SerieLoggee(**data, reps_prevues=reps_prevues, charge_prevue_kg=charge_prevue_kg)
    db.add(serie)
    db.commit()
    db.refresh(serie)
    return serie


@app.patch("/api/series_loggees/{serie_id}", response_model=schemas.SerieLoggeeOut)
def update_serie_loggee(serie_id: int, payload: schemas.SerieLoggeeUpdate, db: Session = Depends(get_db)):
    serie = db.get(models.SerieLoggee, serie_id)
    if not serie:
        raise HTTPException(status_code=404, detail="Série introuvable")
    updates = payload.model_dump(exclude_unset=True)
    if "difficulte" in updates and "rpe_approx" not in updates:
        updates["rpe_approx"] = _rpe_approx_depuis_difficulte(updates["difficulte"])
    for key, value in updates.items():
        setattr(serie, key, int(value) if key == "coche" else value)
    db.commit()
    db.refresh(serie)
    return serie


@app.delete("/api/series_loggees/{serie_id}", status_code=204)
def delete_serie_loggee(serie_id: int, db: Session = Depends(get_db)):
    serie = db.get(models.SerieLoggee, serie_id)
    if not serie:
        raise HTTPException(status_code=404, detail="Série introuvable")
    db.delete(serie)
    db.commit()
    return None


# ---------- Exercices historique ----------

@app.get("/api/exercices_historique", response_model=list[schemas.ExerciceHistoriqueOut])
def list_exercices_historique(nom_exercice: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(models.ExerciceHistorique)
    if nom_exercice:
        query = query.filter(models.ExerciceHistorique.nom_exercice == nom_exercice)
    return query.order_by(models.ExerciceHistorique.date.asc()).all()


@app.post("/api/exercices_historique", response_model=schemas.ExerciceHistoriqueOut)
def create_exercice_historique(payload: schemas.ExerciceHistoriqueCreate, db: Session = Depends(get_db)):
    entry = models.ExerciceHistorique(**payload.model_dump())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


# ---------- Modules intellectuels ----------

@app.get("/api/modules", response_model=list[schemas.ModuleOut])
def list_modules(db: Session = Depends(get_db)):
    return db.query(models.ModuleIntellectuel).all()


@app.get("/api/modules/today", response_model=Optional[schemas.ModuleOut])
def get_today_module(db: Session = Depends(get_db)):
    return db.query(models.ModuleIntellectuel).order_by(models.ModuleIntellectuel.id.asc()).first()


@app.get("/api/modules/{module_id}", response_model=schemas.ModuleOut)
def get_module(module_id: int, db: Session = Depends(get_db)):
    module = db.get(models.ModuleIntellectuel, module_id)
    if not module:
        raise HTTPException(status_code=404, detail="Module introuvable")
    return module


# ---------- Sessions apprentissage ----------

@app.get("/api/sessions_apprentissage", response_model=list[schemas.SessionApprentissageOut])
def list_sessions_apprentissage(db: Session = Depends(get_db)):
    return db.query(models.SessionApprentissage).order_by(models.SessionApprentissage.date.desc()).all()


@app.post("/api/sessions_apprentissage", response_model=schemas.SessionApprentissageOut)
def create_session_apprentissage(payload: schemas.SessionApprentissageCreate, db: Session = Depends(get_db)):
    entry = models.SessionApprentissage(**payload.model_dump())
    db.add(entry)
    db.commit()
    db.refresh(entry)

    today_streak = db.get(models.Streak, entry.date)
    if not today_streak:
        today_streak = models.Streak(date=entry.date, sport_fait=0, apprentissage_fait=1)
        db.add(today_streak)
    else:
        today_streak.apprentissage_fait = 1
    db.commit()
    db.refresh(entry)
    return entry


# ---------- Historique de séances (prévu vs réalisé, contexte, phase calendaire) ----------

@app.get("/api/historique_seances", response_model=list[schemas.HistoriqueSeanceOut])
def list_historique_seances(db: Session = Depends(get_db)):
    return db.query(models.HistoriqueSeance).order_by(models.HistoriqueSeance.date.desc()).all()


@app.post("/api/historique_seances", response_model=schemas.HistoriqueSeanceOut)
def create_historique_seance(payload: schemas.HistoriqueSeanceCreate, db: Session = Depends(get_db)):
    profil = db.query(models.Profil).order_by(models.Profil.id.desc()).first()
    calendrier = profil.calendrier_matchs if profil else None
    phase = compute_phase(payload.date, calendrier)

    entry = models.HistoriqueSeance(**payload.model_dump(), phase_calendaire=phase)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


# ---------- Génération de séance assistée (moteur de règles + Mistral) ----------


def _construire_contexte_historique(db: Session) -> dict:
    """Construit le contexte d'historique attendu par regles_seance.generer_recommandation :
    les 3 dernières séances par type, les 3 dernières toutes confondues, et les zones
    sensibles signalées récemment.

    Note : type_seance n'est renseigné avec les catégories canoniques (force,
    explosivité_vitesse, esthétique, décharge) que pour les séances créées via
    /api/seance/generer. Les entrées historiques créées manuellement avant cet
    endpoint (type_seance = nom libre de la séance) ne matcheront simplement
    aucune catégorie et seront ignorées par le regroupement par type.
    """
    rows = db.query(models.HistoriqueSeance).order_by(models.HistoriqueSeance.date.desc()).limit(30).all()

    par_type: dict[str, list[dict]] = {}
    recent: list[dict] = []
    zones_sensibles_recentes: list[str] = []

    for r in rows:
        entry = {"date": r.date, "rpe": r.rpe, "pourcentage_complete": r.pourcentage_complete}
        par_type.setdefault(r.type_seance, []).append(entry)
        if len(recent) < 3:
            recent.append(entry)
        if r.zone_sensible_signalee and r.zone_sensible_signalee not in zones_sensibles_recentes:
            zones_sensibles_recentes.append(r.zone_sensible_signalee)

    par_type = {k: v[:3] for k, v in par_type.items()}

    return {
        "par_type": par_type,
        "recent": recent,
        "zones_sensibles_recentes": zones_sensibles_recentes[:5],
    }


def _construire_liste_bibliotheque(db: Session) -> list[models.ExerciceBibliotheque]:
    return db.query(models.ExerciceBibliotheque).order_by(models.ExerciceBibliotheque.id.asc()).all()


def _a_historique_reel(exercice_id: int, db: Session) -> bool:
    """Vrai si au moins une série a déjà été loguée (façon Hevy) pour cet exercice :
    dans ce cas la vraie progression (basée sur cet historique) prime sur toute
    charge de départ estimée."""
    return (
        db.query(models.SerieLoggee.id)
        .filter(models.SerieLoggee.exercice_id == exercice_id, models.SerieLoggee.coche == 1)
        .first()
        is not None
    )


def _construire_charges_depart(
    candidats: list[models.ExerciceBibliotheque],
    poids_corps: Optional[float],
    niveau_physique: Optional[str],
    db: Session,
) -> dict[int, float]:
    """Calcule, pour les exercices candidats concernés (charge basée sur le poids
    de corps) et n'ayant pas encore d'historique réel loggé, une charge de départ
    à injecter dans le prompt Mistral comme point de départ à respecter."""
    charges: dict[int, float] = {}
    for ex in candidats:
        if _a_historique_reel(ex.id, db):
            continue  # historique réel disponible : la vraie progression prime
        charge = estimer_charge_depart(ex.nom, poids_corps, niveau_physique)
        if charge is not None:
            charges[ex.id] = charge
    return charges


# Types d'exercices pertinents pour chaque type de séance suggéré par le moteur de règles.
# "gainage_prevention" et "échauffement" sont toujours inclus : le premier doit systématiquement
# figurer en fin de séance (garde-fou ci-dessous), le second sert de mise en route quel que soit
# le type de séance.
TYPES_PAR_TYPE_SEANCE: dict[str, list[str]] = {
    "force": ["force", "force_esthetique", "technique", "gainage_prevention", "échauffement"],
    "explosivité_vitesse": ["explosivité", "vitesse", "agilité", "technique", "gainage_prevention", "échauffement"],
    "esthétique": ["esthetique", "force_esthetique", "gainage_prevention", "échauffement"],
    # Type de séance prévu par le gabarit hebdomadaire d'un programme actif quand l'objectif
    # Endurance / Perte de poids est déclaré (voir generer_programme) — absent du cahier des
    # charges initial du moteur de règles, ajouté pour rester cohérent avec le programme.
    "endurance": ["endurance", "technique", "gainage_prevention", "échauffement"],
    "décharge": ["mobilite_recuperation", "gainage_prevention", "technique", "endurance", "échauffement"],
}

MAX_CANDIDATS_MISTRAL = 18


def _materiel_compatible(materiel_requis: Optional[str], materiel_disponible: str) -> bool:
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


def _groupe_concerne_par_zone_sensible(groupe_musculaire: str, zones_sensibles: list[str]) -> bool:
    gm = (groupe_musculaire or "").lower()
    return any(zone.lower() in gm for zone in zones_sensibles if zone)


def _selectionner_exercices_candidats(
    bibliotheque: list[models.ExerciceBibliotheque],
    type_seance_suggere: str,
    materiel_disponible: str,
    zones_sensibles: list[str],
    max_candidats: int = MAX_CANDIDATS_MISTRAL,
) -> list[models.ExerciceBibliotheque]:
    """Filtre côté backend la bibliothèque avant de l'envoyer à Mistral (au lieu de tout
    envoyer) : type d'exercice pertinent pour le type de séance suggéré, matériel
    disponible, exclusion des zones sensibles déclarées. Garantit qu'au moins un exercice
    de type gainage_prevention est présent (à placer en fin de séance)."""
    types_ok = set(TYPES_PAR_TYPE_SEANCE.get(type_seance_suggere, []))

    def _eligible(ex: models.ExerciceBibliotheque) -> bool:
        if _groupe_concerne_par_zone_sensible(ex.groupe_musculaire, zones_sensibles):
            return False
        if not _materiel_compatible(ex.materiel_requis, materiel_disponible):
            return False
        return True

    candidats = [ex for ex in bibliotheque if _eligible(ex) and (not types_ok or ex.type in types_ok)]

    # Filet de sécurité : si le croisement type/matériel/zones ne renvoie rien (bibliothèque
    # trop restreinte, matériel très limité...), on retombe sur tout ce qui respecte au moins
    # les exclusions de sécurité (matériel, zones sensibles) plutôt que d'envoyer une liste vide.
    if not candidats:
        candidats = [ex for ex in bibliotheque if _eligible(ex)]
    if not candidats:
        candidats = list(bibliotheque)

    candidats = candidats[:max_candidats]

    if not any(ex.type == "gainage_prevention" for ex in candidats):
        secours_gainage = next(
            (ex for ex in bibliotheque if ex.type == "gainage_prevention" and _eligible(ex)),
            next((ex for ex in bibliotheque if ex.type == "gainage_prevention"), None),
        )
        if secours_gainage:
            candidats.append(secours_gainage)

    return candidats


def _construire_seance_secours(
    plan: list[dict], type_seance_suggere: str, rpe_cible: int
) -> dict:
    """Séance de repli, construite sans IA à partir du plan déjà calibré en temps, utilisée
    quand Mistral échoue à renvoyer des exercice_id valides après une nouvelle tentative."""
    autres = [p for p in plan if p["exercice"].type != "gainage_prevention"][:4]
    gainage = next((p for p in plan if p["exercice"].type == "gainage_prevention"), None)

    choisis = autres or list(plan)[:4]
    if gainage and gainage not in choisis:
        choisis.append(gainage)

    exercices = [
        {
            "exercice_id": p["exercice"].id,
            "series": p["series"],
            "repetitions": "10-12",
            "charge_indicative": "poids du corps" if p["exercice"].charge_recommandee == "poids_du_corps" else "à ajuster selon ressenti",
            "notes": None,
            "rpe_cible": rpe_cible,
            "temps_repos_recommande_s": p["temps_repos_recommande_s"],
        }
        for p in choisis
    ]

    return {
        "nom_seance": f"Séance {type_seance_suggere} (générée automatiquement)",
        "duree_min": duree_seance.duree_totale_estimee_min(choisis),
        "exercices": exercices,
        "explication": (
            "Séance de secours générée automatiquement à partir de la bibliothèque d'exercices : "
            "le générateur IA n'a pas renvoyé de sélection valide après une nouvelle tentative."
        ),
    }


def _corriger_charges_poids_du_corps(exercices: list[dict], charge_recommandee_par_id: dict[int, str]) -> None:
    """Garde-fou post-génération : si Mistral renvoie malgré tout une charge non nulle sur un
    exercice marqué poids_du_corps dans la bibliothèque, force "charge_indicative" à "poids du
    corps" plutôt que de relancer un appel Mistral supplémentaire (coût inutile pour une simple
    correction de valeur)."""
    for item in exercices:
        if charge_recommandee_par_id.get(item.get("exercice_id")) != "poids_du_corps":
            continue
        charge = item.get("charge_indicative")
        if isinstance(charge, str) and "poids du corps" in charge.lower():
            continue
        if charge in (None, "", "0", 0):
            continue
        logger.warning(
            "Charge non nulle (%r) reçue de Mistral pour un exercice poids_du_corps (id %s) : "
            "forcée à « poids du corps ».",
            charge,
            item.get("exercice_id"),
        )
        item["charge_indicative"] = "poids du corps"


def _appliquer_calibrage_temps(exercices: list[dict], plan: list[dict], rpe_cible: int) -> None:
    """Garde-fou post-génération : impose series / temps_repos_recommande_s à partir du plan
    calculé côté serveur (duree_seance.calibrer_exercices) et rpe_cible par défaut, plutôt que
    de laisser Mistral décider seul du respect du temps disponible."""
    plan_par_id = {item["exercice"].id: item for item in plan}
    for item in exercices:
        p = plan_par_id.get(item.get("exercice_id"))
        if p is None:
            continue
        item["series"] = p["series"]
        item["temps_repos_recommande_s"] = p["temps_repos_recommande_s"]
        if not isinstance(item.get("rpe_cible"), int):
            item["rpe_cible"] = rpe_cible


# Type de séance du gabarit hebdomadaire (voir generer_programme) -> clé correspondante dans
# trajectoire_progression. Les deux vocabulaires diffèrent volontairement (accents, découpage) :
# la génération de programme (Mistral) produit trajectoire_progression avec ces clés précises.
TRAJECTOIRE_CLE_PAR_TYPE_SEANCE_GABARIT: dict[str, str] = {
    "force": "force",
    "explosivité_vitesse": "explosivite",
    "esthétique": "esthetique",
    "endurance": "endurance",
}


def _semaine_courante_programme(programme: models.Programme, aujourdhui: date) -> int:
    """Semaine en cours du programme (1-indexée, plafonnée à duree_semaines) — même formule
    que semaineActuelle() côté frontend (src/utils/programme.ts), à garder synchronisée."""
    jours = (aujourdhui - programme.date_debut).days
    semaine = jours // 7 + 1
    return min(max(semaine, 1), programme.duree_semaines)


def _phase_programme_pour_semaine(programme: models.Programme, semaine: int) -> Optional[dict]:
    for phase in programme.phases or []:
        if phase.get("semaine_debut") <= semaine <= phase.get("semaine_fin"):
            return phase
    return None


def _charge_cible_programme(programme: models.Programme, type_seance_gabarit: Optional[str], semaine: int) -> Optional[float]:
    """Charge/volume cible (en % relatif à la semaine 1) prévu par trajectoire_progression
    pour ce type de séance et cette semaine, ou None si non défini (ex: type non suivi par la
    trajectoire, ou semaine hors bornes des valeurs générées)."""
    cle = TRAJECTOIRE_CLE_PAR_TYPE_SEANCE_GABARIT.get(type_seance_gabarit or "")
    if not cle:
        return None
    valeurs = (programme.trajectoire_progression or {}).get(cle) or []
    if 1 <= semaine <= len(valeurs):
        return valeurs[semaine - 1]
    return None


def _construire_system_prompt() -> str:
    notes = connaissances.get_notes_generation_ia()
    notes_txt = "\n".join(f"- {n}" for n in notes)
    return (
        "Tu es un coach sportif spécialisé en préparation physique football. "
        "Règles de comportement à respecter systématiquement, sans exception :\n"
        f"{notes_txt}\n"
        "- Pour chaque exercice, respecte strictement le champ charge_recommandee fourni. "
        "Ne propose jamais de charge lourde sur un exercice marqué poids_du_corps ou "
        "charge_legere, même si l'utilisateur a un bon niveau de force déclaré — la nature "
        "de l'exercice prime sur le niveau de l'utilisateur."
    )


def _construire_prompt_generation(
    profil: dict,
    recommandation: dict,
    etat_du_jour: dict,
    plan: list[dict],
    fiches_theoriques: list[str],
    charges_depart: Optional[dict[int, float]] = None,
    rpe_cible: int = duree_seance.RPE_CIBLE_DEFAUT,
) -> str:
    exclusions = recommandation.get("exclusions") or []
    exclusions_txt = ", ".join(exclusions) if exclusions else "aucune"
    raisons_txt = "; ".join(recommandation.get("raisons") or []) or "aucune"

    programme_ctx = recommandation.get("programme")
    programme_txt = ""
    if programme_ctx:
        charge_cible = programme_ctx.get("charge_cible_pct")
        charge_cible_txt = f"{charge_cible:+.0f}% (relatif à la semaine 1)" if charge_cible is not None else "non définie pour ce type de séance"
        programme_txt = f"""

CONTEXTE DU PROGRAMME EN COURS (trame de moyen terme sur {programme_ctx['duree_semaines']} semaines — la
RECOMMANDATION CALCULÉE PAR LE MOTEUR DE RÈGLES ci-dessous garde la priorité en cas de conflit,
mais respecte cette trame sinon)
- Semaine {programme_ctx['semaine_courante']}/{programme_ctx['duree_semaines']}
- Phase actuelle du programme : {programme_ctx.get('phase_nom') or 'non définie'} — {programme_ctx.get('phase_description') or ''}
- Type de séance prévu par le gabarit hebdomadaire pour aujourd'hui : {programme_ctx.get('type_seance_gabarit') or 'non défini'}
- Charge/volume cible de la trajectoire de progression pour cette semaine et ce type de séance : {charge_cible_txt}"""

    charges_depart = charges_depart or {}

    def _ligne_bibliotheque(item: dict) -> str:
        ex: models.ExerciceBibliotheque = item["exercice"]
        ligne = (
            f"- id {ex.id} : {ex.nom} (groupe musculaire : {ex.groupe_musculaire}, type : {ex.type}, "
            f"charge_recommandee : {ex.charge_recommandee}) — nombre de séries imposé : {item['series']} "
            f"(déjà calibré selon le temps disponible, ne pas le modifier)"
        )
        charge = charges_depart.get(ex.id)
        if charge is not None:
            ligne += f" — {formater_recommandation_charge(charge)}"
        return ligne

    bibliotheque_txt = "\n".join(_ligne_bibliotheque(item) for item in plan)

    fiches_txt = "\n\n".join(fiches_theoriques) if fiches_theoriques else "aucune"

    return f"""Tu es un coach sportif qui construit une séance de sport concrète pour un joueur de football amateur.

EXERCICES DISPONIBLES (présélection déjà filtrée pour ce joueur selon le type de séance, le matériel
disponible, ses zones sensibles ET le temps disponible aujourd'hui — tu dois obligatoirement choisir
les exercices de la séance UNIQUEMENT parmi cette liste, en référençant leur id ; interdiction
stricte d'inventer un exercice ou de référencer un id qui n'y figure pas)
{bibliotheque_txt}

CONTRAINTE DE TEMPS DÉJÀ CALCULÉE : le nombre de séries de chaque exercice ci-dessus a déjà été
calculé côté serveur pour que la séance tienne dans le temps disponible déclaré par le joueur
(échauffement + exécution + repos entre séries). Reprends exactement ce nombre de séries dans
"series" pour chaque exercice — ne l'augmente ni ne le diminue.

RPE cible pour cette séance (indicatif, à reprendre tel quel pour le champ "rpe_cible" de chaque
exercice, sauf raison technique particulière propre à un exercice) : {rpe_cible}/10.

Chaque exercice ci-dessus porte un champ charge_recommandee (poids_du_corps, charge_legere,
charge_moderee ou charge_lourde_progressive) qui indique la nature de charge adaptée à cet
exercice, indépendamment du niveau de force du joueur. Respecte-le strictement : pour un exercice
marqué poids_du_corps, "charge_indicative" doit valoir "poids du corps" (aucune charge externe,
même légère) ; pour un exercice marqué charge_legere, ne propose qu'une charge légère.

Pour les exercices ci-dessus portant une « charge de départ recommandée », cette valeur a été
calculée côté serveur (poids de corps + niveau déclaré, aucun historique réel disponible pour cet
exercice) : reprends-la telle quelle dans "charge_indicative" pour cet exercice, sans l'inventer
ni la modifier sans raison. Pour les autres exercices avec charge, indique une charge indicative
raisonnable comme d'habitude, cohérente avec le champ charge_recommandee.

CONTRAINTE OBLIGATOIRE : inclure au moins un exercice de type gainage_prevention (voir liste
ci-dessus) et le placer en dernière position de la liste "exercices" (fin de séance).

PROFIL
- Poste : {profil.get('poste')}
- Niveau physique global : {profil.get('niveau_physique')}
- Qualités physiques déclarées (1 à 5) : {profil.get('niveaux_qualites_physiques')}
- Matériel disponible : {profil.get('materiel')}
- Contraintes de temps habituelles : {profil.get('contraintes_temps')}

ÉTAT DU JOUR (déclaré par le joueur)
- Sommeil : {etat_du_jour.get('sommeil') or 'non renseigné'}
- Motivation : {etat_du_jour.get('motivation') or 'non renseignée'}
- Temps disponible aujourd'hui : {etat_du_jour.get('temps_dispo') or 'non renseigné'}
- Entraînements club cette semaine : {etat_du_jour.get('entrainement_club_semaine') or 'non renseigné'}
- Envie du moment : {etat_du_jour.get('envie_texte') or 'aucune précision'}

RECOMMANDATION CALCULÉE PAR LE MOTEUR DE RÈGLES (contrainte à respecter impérativement,
ne dépend pas de l'envie du joueur ci-dessus)
- Phase calendaire : {recommandation['phase_calendaire']}
- Intensité maximale autorisée : {recommandation['intensite_max']} — NE PAS LA DÉPASSER, quelle que soit l'envie exprimée par le joueur.
- Priorités liées au poste : {', '.join(recommandation['priorites_poste']) or 'aucune priorité spécifique'}
- Type de séance à produire : {recommandation['type_seance_suggere']}
- Ajustement à appliquer par rapport à la dernière séance de ce type : charge {recommandation['ajustement_charge_pct']:+.0f}%, volume {recommandation.get('ajustement_volume_pct', 0):+.0f}%
- Zones à exclure impérativement de la séance (aucun exercice ne doit les solliciter) : {exclusions_txt}
- Raisons de ces contraintes : {raisons_txt}
{programme_txt}

CONNAISSANCES THÉORIQUES DE RÉFÉRENCE (à utiliser pour enrichir l'explication de la séance,
jamais pour contredire la recommandation calculée ci-dessus)
{fiches_txt}

CONSIGNE
Construis une séance concrète respectant strictement l'intensité maximale et les exclusions
ci-dessus, cohérente avec le poste et le matériel disponible, en choisissant exclusivement des
exercices dont l'id figure dans la liste EXERCICES DISPONIBLES ci-dessus.
Réponds UNIQUEMENT avec un objet JSON valide, sans aucun texte avant ni après, au format exact
suivant :
{{
  "nom_seance": "string",
  "duree_min": nombre entier de minutes,
  "exercices": [
    {{"exercice_id": nombre entier (id pris dans la liste EXERCICES DISPONIBLES), "series": nombre entier (celui imposé ci-dessus), "repetitions": "string", "charge_indicative": "string", "rpe_cible": nombre entier, "notes": "string"}}
  ],
  "explication": "texte en français expliquant le pourquoi de cette séance (phase calendaire, poste, état du jour)"
}}"""


def _calculer_xp(rpe: Optional[int], pourcentage_complete: Optional[float], streak_actuel: int) -> int:
    """Calcule l'XP gagné pour une séance terminée. Calcul Python simple, pas Mistral."""
    xp = 10  # base

    if pourcentage_complete is not None:
        if pourcentage_complete >= 100:
            xp += 10
        elif pourcentage_complete >= 80:
            xp += 5

    if streak_actuel >= 7:
        xp += 10
    elif streak_actuel >= 3:
        xp += 5

    return xp


@app.post("/api/seance/generer", response_model=schemas.SeanceGenereeOut)
def generer_seance(
    payload: schemas.EtatDuJour, db: Session = Depends(get_db), today: date = Depends(get_current_date)
):
    profil = db.query(models.Profil).order_by(models.Profil.id.desc()).first()
    if not profil:
        raise HTTPException(status_code=400, detail="Aucun profil enregistré : termine l'onboarding avant de générer une séance.")

    bibliotheque = _construire_liste_bibliotheque(db)
    if not bibliotheque:
        raise HTTPException(
            status_code=400,
            detail="La bibliothèque d'exercices est vide : impossible de générer une séance tant qu'elle n'est pas peuplée.",
        )

    profil_dict = schemas.ProfilOut.model_validate(profil).model_dump(mode="json")
    historique_ctx = _construire_contexte_historique(db)
    etat_du_jour = payload.model_dump()

    # ---- Programme actif : cadre hebdomadaire (gabarit + trajectoire + phase) ----
    # Sert de base au type de séance du jour ; le moteur de règles calendaire (phase match,
    # historique récent, garde-fous) reste appliqué par-dessus et garde la priorité en cas de
    # conflit (cf. regles_seance._suggerer_type_seance). Sans programme actif (edge case), ce
    # bloc ne fait rien et le comportement retombe sur l'ancien flux (génération libre).
    programme = (
        db.query(models.Programme).filter(models.Programme.statut == "actif").order_by(models.Programme.id.desc()).first()
    )
    type_seance_gabarit: Optional[str] = None
    programme_ctx: Optional[dict] = None

    if programme:
        semaine_courante = _semaine_courante_programme(programme, today)
        phase_programme = _phase_programme_pour_semaine(programme, semaine_courante)
        # gabarit_hebdomadaire est keyé par jour ABRÉGÉ ("Lun", "Mer", ...), pas le nom complet
        # ("Lundi") utilisé pour calendrier_matchs.jour_habituel — voir regles_seance.py.
        jour_abbrev = regles_seance.JOURS_SEMAINE_ABBREV[today.weekday()]
        type_seance_gabarit_brut = (programme.gabarit_hebdomadaire or {}).get(jour_abbrev)
        # Tolère une valeur renvoyée par Mistral légèrement différente de la casse/des accents
        # canoniques (déjà observé en production) plutôt que de la traiter comme absente.
        type_seance_gabarit = _normaliser_type_seance_programme(type_seance_gabarit_brut)

        if type_seance_gabarit == "repos" and not etat_du_jour.get("forcer_seance_legere"):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Jour de repos prévu par ton programme aujourd'hui "
                    f"(semaine {semaine_courante}/{programme.duree_semaines}). "
                    "Renvoie forcer_seance_legere=true pour générer quand même une séance légère."
                ),
            )

        if type_seance_gabarit == "repos":
            # forcer_seance_legere=true : repos prévu mais séance légère demandée malgré tout.
            type_seance_gabarit = "décharge"

        charge_cible_pct = _charge_cible_programme(programme, type_seance_gabarit, semaine_courante)
        programme_ctx = {
            "semaine_courante": semaine_courante,
            "duree_semaines": programme.duree_semaines,
            "phase_nom": phase_programme.get("nom") if phase_programme else None,
            "phase_description": phase_programme.get("description") if phase_programme else None,
            "type_seance_gabarit": type_seance_gabarit,
            "charge_cible_pct": charge_cible_pct,
        }

    recommandation = regles_seance.generer_recommandation(
        profil_dict, historique_ctx, etat_du_jour, type_seance_gabarit=type_seance_gabarit, aujourdhui=today
    )

    if programme_ctx is not None:
        recommandation["programme"] = programme_ctx
        if type_seance_gabarit and recommandation["type_seance_suggere"] != type_seance_gabarit:
            # Transparence : le moteur de règles calendaire a supplanté ce que prévoyait le gabarit.
            recommandation["raisons"].append(
                f"Programme actif (semaine {programme_ctx['semaine_courante']}/{programme_ctx['duree_semaines']}) prévoyait "
                f"« {type_seance_gabarit} » aujourd'hui, mais le moteur de règles calendaire impose "
                f"« {recommandation['type_seance_suggere']} » (priorité au calendrier)."
            )

    type_force = etat_du_jour.get("type_seance_force")
    decharge_securite = recommandation["type_seance_suggere"] == "décharge" and any(
        "mode semaine de décharge activé" in raison for raison in recommandation.get("raisons") or []
    )
    if type_force and type_force in TYPES_PAR_TYPE_SEANCE and not decharge_securite:
        if type_force != recommandation["type_seance_suggere"]:
            recommandation["raisons"].append(
                f"Type de séance forcé manuellement à « {type_force} » (au lieu de « {recommandation['type_seance_suggere']} » suggéré par le moteur de règles)."
            )
        recommandation["type_seance_suggere"] = type_force

    zone_sensible = (recommandation.get("exclusions") or [None])[0]
    zones_sensibles = historique_ctx.get("zones_sensibles_recentes") or []
    candidats = _selectionner_exercices_candidats(
        bibliotheque,
        recommandation["type_seance_suggere"],
        profil_dict.get("materiel") or "",
        zones_sensibles,
    )

    temps_dispo_min = duree_seance.parser_temps_dispo_minutes(etat_du_jour.get("temps_dispo"))
    plan = duree_seance.calibrer_exercices(candidats, temps_dispo_min)
    rpe_cible = duree_seance.rpe_cible_pour_intensite(recommandation.get("intensite_max"))

    logger.info(
        "Génération séance : type_seance_suggere=%s, temps_dispo=%s min -> %d candidat(s) calibré(s) envoyé(s) à Mistral : %s",
        recommandation["type_seance_suggere"],
        temps_dispo_min,
        len(plan),
        [(p["exercice"].id, p["exercice"].type, p["series"]) for p in plan],
    )

    fiches_theoriques = connaissances.selectionner_fiches_pertinentes(
        recommandation["type_seance_suggere"], profil_dict.get("poste"), zone_sensible
    )
    charges_depart = _construire_charges_depart(
        [p["exercice"] for p in plan], profil_dict.get("poids_kg"), profil_dict.get("niveau_physique"), db
    )
    system_prompt = _construire_system_prompt()
    prompt = _construire_prompt_generation(
        profil_dict, recommandation, etat_du_jour, plan, fiches_theoriques, charges_depart, rpe_cible
    )

    ids_valides = {p["exercice"].id for p in plan}
    charge_recommandee_par_id = {p["exercice"].id: p["exercice"].charge_recommandee for p in plan}
    required_keys = {"nom_seance", "duree_min", "exercices", "explication"}
    data: Optional[dict] = None

    for tentative in range(2):  # un essai, puis une seule retentative en cas de sortie invalide
        try:
            reponse = mistral_client.appeler_mistral_json(prompt, system_prompt=system_prompt)
        except mistral_client.MistralError as exc:
            logger.error("Échec de la génération de séance via Mistral (tentative %s) : %s", tentative + 1, exc)
            continue

        if not required_keys.issubset(reponse) or not isinstance(reponse.get("exercices"), list) or not reponse["exercices"]:
            logger.warning("Réponse Mistral incomplète ou invalide (tentative %s) : %s", tentative + 1, reponse)
            continue

        if not all(isinstance(item, dict) and item.get("exercice_id") in ids_valides for item in reponse["exercices"]):
            logger.warning("Réponse Mistral avec exercice_id hors sélection (tentative %s) : %s", tentative + 1, reponse)
            continue

        _corriger_charges_poids_du_corps(reponse["exercices"], charge_recommandee_par_id)
        _appliquer_calibrage_temps(reponse["exercices"], plan, rpe_cible)
        data = reponse
        break

    if data is None:
        logger.error("Génération de séance IA impossible après retentative : repli sur une séance de secours.")
        data = _construire_seance_secours(plan, recommandation["type_seance_suggere"], rpe_cible)

    duree_calibree_min = duree_seance.duree_totale_estimee_min(plan)

    seance = models.Seance(
        date=today,
        nom=data["nom_seance"],
        exercices=data["exercices"],
        statut="prévue",
        type_seance=recommandation["type_seance_suggere"],
        explication=data.get("explication"),
        duree_prevue=duree_calibree_min,
        duree_reelle=None,
    )
    db.add(seance)
    db.commit()
    db.refresh(seance)

    return schemas.SeanceGenereeOut(
        id=seance.id,
        nom_seance=data["nom_seance"],
        # Durée calculée en code à partir du calibrage temps_dispo, pas la valeur libre renvoyée
        # par Mistral (voir duree_seance.py) : c'est cette estimation qui a servi à limiter les
        # exercices/séries, donc c'est elle qui doit être affichée et comparée à la durée réelle.
        duree_min=duree_calibree_min,
        exercices=data["exercices"],
        explication=data.get("explication", ""),
        recommandation=recommandation,
    )


@app.post("/api/seance/terminer", response_model=schemas.TerminerSeanceOut)
def terminer_seance(payload: schemas.TerminerSeancePayload, db: Session = Depends(get_db)):
    """Calcule la fin de séance à partir des vraies données de series_loggees
    (plus d'IA pour interpréter un compte-rendu texte libre). Le RPE est déduit de la
    moyenne des validations rapides (facile/comme prévu/dur) de chaque série, sauf
    override manuel explicite ; `note` reste un texte libre optionnel pour le
    ressenti général, conservé tel quel sans traitement IA."""
    seance = db.get(models.Seance, payload.seance_id)
    if not seance:
        raise HTTPException(status_code=404, detail="Séance introuvable")

    series = db.query(models.SerieLoggee).filter(models.SerieLoggee.seance_id == seance.id).all()
    series_validees = [s for s in series if s.coche]

    volume_total = sum((s.poids_kg or 0) * (s.repetitions or 0) for s in series_validees)
    nb_series_validees = len(series_validees)

    series_prevues = sum(int(item.get("series") or 0) for item in (seance.exercices or []) if isinstance(item, dict))
    pourcentage_complete = round(100 * nb_series_validees / series_prevues, 1) if series_prevues > 0 else None

    exercices_ids = sorted({s.exercice_id for s in series_validees})
    bibliotheque_par_id = {
        ex.id: ex for ex in db.query(models.ExerciceBibliotheque).filter(models.ExerciceBibliotheque.id.in_(exercices_ids)).all()
    } if exercices_ids else {}

    exercices_realises = []
    for exercice_id in exercices_ids:
        series_exercice = sorted((s for s in series_validees if s.exercice_id == exercice_id), key=lambda s: s.numero_serie)
        exercices_realises.append(
            {
                "exercice_id": exercice_id,
                "nom": bibliotheque_par_id[exercice_id].nom if exercice_id in bibliotheque_par_id else None,
                "series": [{"numero_serie": s.numero_serie, "poids_kg": s.poids_kg, "repetitions": s.repetitions} for s in series_exercice],
            }
        )

    # RPE de la séance : moyenne des rpe_approx (facile/comme prévu/dur) des séries validées,
    # sauf override manuel explicite dans le payload. C'est cette valeur qui alimente le
    # moteur de règles pour la charge de la prochaine séance du même type.
    rpe_approx_valeurs = [s.rpe_approx for s in series_validees if s.rpe_approx is not None]
    rpe_calcule = round(sum(rpe_approx_valeurs) / len(rpe_approx_valeurs)) if rpe_approx_valeurs else None
    rpe = payload.rpe if payload.rpe is not None else rpe_calcule

    seance.statut = "terminee"
    seance.rpe = rpe
    seance.note = payload.note
    if payload.duree_reelle_min is not None:
        seance.duree_reelle = payload.duree_reelle_min
    db.commit()

    today_streak = db.get(models.Streak, seance.date)
    if not today_streak:
        today_streak = models.Streak(date=seance.date, sport_fait=1, apprentissage_fait=0)
        db.add(today_streak)
    else:
        today_streak.sport_fait = 1
    db.commit()

    xp_gagne = _calculer_xp(rpe, pourcentage_complete, _current_streak(db))

    profil = db.query(models.Profil).order_by(models.Profil.id.desc()).first()
    calendrier = profil.calendrier_matchs if profil else None
    phase = compute_phase(seance.date, calendrier)

    resume = {
        "exercices_realises": exercices_realises,
        "rpe": rpe,
        "pourcentage_complete": pourcentage_complete,
        "volume_total_kg": volume_total,
        "nb_series_validees": nb_series_validees,
        "notes": payload.note,
        # Comparaison temps prévu vs temps réel, pour affiner les estimations de durée
        # par exercice au fil du temps (duree_seance.py).
        "duree_prevue_min": seance.duree_prevue,
        "duree_reelle_min": seance.duree_reelle,
    }

    historique = models.HistoriqueSeance(
        date=seance.date,
        phase_calendaire=phase,
        type_seance=seance.type_seance or seance.nom,
        exercices_prevus=seance.exercices,
        exercices_realises=exercices_realises,
        rpe=rpe,
        pourcentage_complete=pourcentage_complete,
        zone_sensible_signalee=None,
        xp_gagne=xp_gagne,
        notes=payload.note,
        etat_declare_avant={},
    )
    db.add(historique)
    db.commit()
    db.refresh(historique)

    return schemas.TerminerSeanceOut(resume=resume, xp_gagne=xp_gagne, historique_id=historique.id)


# ---------- Programme structuré (8 semaines, indépendant de /api/seance/generer) ----------

DUREE_SEMAINES_PROGRAMME_DEFAUT = 8


TYPES_SEANCE_PROGRAMME = ["force", "explosivité_vitesse", "esthétique", "endurance", "repos"]


def _normaliser_type_seance_programme(valeur: Optional[str]) -> Optional[str]:
    """Fait correspondre une valeur de gabarit_hebdomadaire à un type canonique de
    TYPES_SEANCE_PROGRAMME, tolérant une casse ou des accents légèrement différents de ce
    que demande le prompt (déjà observé en pratique dans les réponses Mistral). Retourne None
    si aucune correspondance, y compris si la valeur est absente (jour non couvert par le
    gabarit) — à distinguer d'une vraie valeur invalide au moment de la génération (voir
    generer_programme, qui rejette et retente plutôt que de stocker une valeur non reconnue)."""
    if not isinstance(valeur, str) or not valeur.strip():
        return None

    def _sans_accents(s: str) -> str:
        for a, b in (("é", "e"), ("è", "e"), ("ê", "e"), ("à", "a")):
            s = s.replace(a, b)
        return s

    cible = _sans_accents(valeur.strip().lower())
    for type_ in TYPES_SEANCE_PROGRAMME:
        if cible == _sans_accents(type_.lower()):
            return type_
    return None


def _construire_system_prompt_programme() -> str:
    return (
        "Tu es un préparateur physique spécialisé en football qui construit un programme "
        "structuré sur plusieurs semaines. Règles impératives :\n"
        "- Ne planifie jamais plus de séances par semaine que le nombre de jours disponibles "
        "déclarés par le joueur : n'invente aucune séance supplémentaire.\n"
        "- Prends en compte TOUS les objectifs déclarés par le joueur (pas seulement son poste "
        "et son calendrier de matchs) pour construire le gabarit_hebdomadaire et la "
        "trajectoire_progression : si l'objectif « Endurance » ou « Perte de poids » est déclaré, "
        "le gabarit_hebdomadaire doit obligatoirement inclure une proportion adaptée de séances de "
        "type endurance (au moins une par semaine si le nombre de jours disponibles le permet), et "
        "la trajectoire_progression doit inclure une entrée « endurance ».\n"
        "- Équilibre les types de séance (force, explosivité_vitesse, esthétique, endurance) selon "
        "les priorités physiques du poste du joueur ET selon ses objectifs déclarés — les deux "
        "comptent, ni l'un ni l'autre ne doit être ignoré.\n"
        "- La progression de charge/volume doit être prudente et réaliste : jamais plus de "
        "5 à 8% de progression cumulée par semaine.\n"
        "- Ne place jamais de séance de type force lourde la veille du jour de match habituel "
        "déclaré : positionne intelligemment le gabarit hebdomadaire par rapport à ce jour."
    )


def _construire_prompt_programme(profil: dict, fiches_theoriques: list[str], jours_dispo: list[str]) -> str:
    fiches_txt = "\n\n".join(fiches_theoriques) if fiches_theoriques else "aucune"
    jour_match = (profil.get("calendrier_matchs") or {}).get("jour_habituel") or "non renseigné"
    objectifs = profil.get("objectifs") or []
    types_txt = " | ".join(f'"{t}"' for t in TYPES_SEANCE_PROGRAMME)

    return f"""Construis un programme d'entraînement physique structuré sur {DUREE_SEMAINES_PROGRAMME_DEFAUT} semaines
pour un joueur de football amateur, à partir de son profil complet.

PROFIL
- Objectifs déclarés (à respecter TOUS dans le gabarit_hebdomadaire et la trajectoire_progression,
  pas seulement le poste et le calendrier) : {objectifs}
- Poste : {profil.get('poste')}
- Niveau physique global : {profil.get('niveau_physique')}
- Qualités physiques déclarées (1 à 5) : {profil.get('niveaux_qualites_physiques')}
- Jour de match habituel : {jour_match}
- Entraînements club : {(profil.get('calendrier_matchs') or {}).get('entrainements_club')}
- Jours disponibles déclarés (ne pas en inventer d'autres) : {jours_dispo}
- Durée par séance / contraintes de temps : {profil.get('contraintes_temps')}
- Matériel disponible : {profil.get('materiel')}
- Objectif esthétique : {profil.get('objectif_esthetique')}

CONNAISSANCES THÉORIQUES DE RÉFÉRENCE (périodisation, chronologie des adaptations, priorités du poste)
{fiches_txt}

CONSIGNE
Réponds UNIQUEMENT avec un objet JSON valide, sans aucun texte avant ni après, au format exact suivant :
{{
  "phases": [
    {{"nom": "adaptation", "semaine_debut": 1, "semaine_fin": 2, "description": "string (intention de ce bloc)"}},
    {{"nom": "accumulation", "semaine_debut": 3, "semaine_fin": 6, "description": "string"}},
    {{"nom": "évaluation", "semaine_debut": 7, "semaine_fin": 8, "description": "string"}}
  ],
  "gabarit_hebdomadaire": {{"<jour parmi {jours_dispo}>": {types_txt}, "...": "..."}},
  "trajectoire_progression": {{
    "force": [8 nombres, progression en % relatif à la semaine 1 (100 = point de départ)],
    "explosivite": [8 nombres, même logique],
    "esthetique": [8 nombres, même logique],
    "endurance": [8 nombres, même logique — obligatoire si « Endurance » ou « Perte de poids » figure dans les objectifs déclarés]
  }}
}}

Le gabarit_hebdomadaire doit contenir une entrée pour chacun des jours disponibles déclarés ci-dessus,
et uniquement ceux-là. La trajectoire_progression doit contenir exactement {DUREE_SEMAINES_PROGRAMME_DEFAUT}
valeurs par qualité, en progression prudente (jamais plus de 5 à 8% cumulés par semaine). N'inclus la clé
"endurance" dans trajectoire_progression que si au moins un jour du gabarit_hebdomadaire est de type
"endurance"."""


def _construire_programme_secours(jours_dispo: list[str], objectifs: list[str]) -> dict:
    """Programme de repli, construit sans IA, utilisé si Mistral échoue après retentative."""
    objectifs_lower = [o.lower() for o in (objectifs or [])]
    veut_endurance = any(o in objectifs_lower for o in ("endurance", "perte de poids"))

    types_cycle = ["force", "explosivité_vitesse", "esthétique", "endurance"] if veut_endurance else ["force", "explosivité_vitesse", "esthétique"]
    gabarit = {jour: types_cycle[i % len(types_cycle)] for i, jour in enumerate(jours_dispo)} if jours_dispo else {}
    progression = [round(100 + i * 5, 1) for i in range(DUREE_SEMAINES_PROGRAMME_DEFAUT)]

    trajectoire = {
        "force": progression,
        "explosivite": progression,
        "esthetique": progression,
    }
    if veut_endurance:
        trajectoire["endurance"] = progression

    return {
        "phases": [
            {"nom": "adaptation", "semaine_debut": 1, "semaine_fin": 2, "description": "Reprise progressive, apprentissage des mouvements."},
            {"nom": "accumulation", "semaine_debut": 3, "semaine_fin": 6, "description": "Montée en charge et en volume."},
            {"nom": "évaluation", "semaine_debut": 7, "semaine_fin": 8, "description": "Consolidation et bilan des progrès."},
        ],
        "gabarit_hebdomadaire": gabarit,
        "trajectoire_progression": trajectoire,
    }


@app.post("/api/programme/generer", response_model=schemas.ProgrammeOut)
def generer_programme(payload: schemas.ProgrammeGenererPayload, db: Session = Depends(get_db)):
    profil = db.query(models.Profil).order_by(models.Profil.id.desc()).first()
    if not profil:
        raise HTTPException(status_code=400, detail="Aucun profil enregistré : termine l'onboarding avant de générer un programme.")

    utilisateur_id = payload.utilisateur_id if payload.utilisateur_id is not None else profil.id
    profil_dict = schemas.ProfilOut.model_validate(profil).model_dump(mode="json")

    jours_dispo = [j.strip() for j in (profil_dict.get("contraintes_temps") or "").split("·")[0].split("/") if j.strip()]

    fiches_theoriques = connaissances.selectionner_fiches_programme(profil_dict.get("poste"))
    system_prompt = _construire_system_prompt_programme()
    prompt = _construire_prompt_programme(profil_dict, fiches_theoriques, jours_dispo)

    required_keys = {"phases", "gabarit_hebdomadaire", "trajectoire_progression"}
    data: Optional[dict] = None

    for tentative in range(2):  # un essai, puis une seule retentative en cas de sortie invalide
        try:
            reponse = mistral_client.appeler_mistral_json(prompt, system_prompt=system_prompt)
        except mistral_client.MistralError as exc:
            logger.error("Échec de la génération de programme via Mistral (tentative %s) : %s", tentative + 1, exc)
            continue

        if not required_keys.issubset(reponse) or not isinstance(reponse.get("phases"), list) or not reponse["phases"]:
            logger.warning("Réponse Mistral incomplète ou invalide pour le programme (tentative %s) : %s", tentative + 1, reponse)
            continue

        # Valide et normalise gabarit_hebdomadaire : chaque valeur doit correspondre à un type
        # canonique de TYPES_SEANCE_PROGRAMME (une casse/accentuation légèrement différente est
        # tolérée et corrigée), sinon la réponse est rejetée et une nouvelle tentative est faite
        # plutôt que de stocker une valeur qui n'apparaîtra jamais correctement à l'écran.
        gabarit_brut = reponse.get("gabarit_hebdomadaire")
        if not isinstance(gabarit_brut, dict) or not gabarit_brut:
            logger.warning("gabarit_hebdomadaire absent ou vide pour le programme (tentative %s) : %s", tentative + 1, reponse)
            continue

        gabarit_normalise: dict[str, str] = {}
        gabarit_valide = True
        for jour, type_brut in gabarit_brut.items():
            type_norm = _normaliser_type_seance_programme(type_brut)
            if type_norm is None:
                logger.warning(
                    "Type de séance non reconnu dans gabarit_hebdomadaire (tentative %s) : jour=%r valeur=%r",
                    tentative + 1,
                    jour,
                    type_brut,
                )
                gabarit_valide = False
                break
            gabarit_normalise[jour] = type_norm

        if not gabarit_valide:
            continue

        reponse["gabarit_hebdomadaire"] = gabarit_normalise
        data = reponse
        break

    if data is None:
        logger.error("Génération de programme IA impossible après retentative : repli sur un programme de secours.")
        data = _construire_programme_secours(jours_dispo, profil_dict.get("objectifs") or [])

    # Un seul programme actif à la fois : on clôt l'ancien avant de créer le nouveau.
    db.query(models.Programme).filter(
        models.Programme.utilisateur_id == utilisateur_id, models.Programme.statut == "actif"
    ).update({"statut": "terminé"})
    db.commit()

    programme = models.Programme(
        utilisateur_id=utilisateur_id,
        date_debut=date.today(),
        duree_semaines=DUREE_SEMAINES_PROGRAMME_DEFAUT,
        phases=data["phases"],
        gabarit_hebdomadaire=data["gabarit_hebdomadaire"],
        trajectoire_progression=data["trajectoire_progression"],
        statut="actif",
    )
    db.add(programme)
    db.commit()
    db.refresh(programme)

    return programme


@app.get("/api/programme/actif", response_model=Optional[schemas.ProgrammeOut])
def get_programme_actif(db: Session = Depends(get_db)):
    return (
        db.query(models.Programme)
        .filter(models.Programme.statut == "actif")
        .order_by(models.Programme.id.desc())
        .first()
    )


# ---------- Streaks ----------

@app.get("/api/streaks", response_model=list[schemas.StreakOut])
def list_streaks(days: int = 35, db: Session = Depends(get_db)):
    since = date.today() - timedelta(days=days - 1)
    rows = db.query(models.Streak).filter(models.Streak.date >= since).order_by(models.Streak.date.asc()).all()
    by_date = {r.date: r for r in rows}
    result = []
    for i in range(days):
        d = since + timedelta(days=i)
        row = by_date.get(d)
        result.append(
            schemas.StreakOut(
                date=d,
                sport_fait=bool(row.sport_fait) if row else False,
                apprentissage_fait=bool(row.apprentissage_fait) if row else False,
            )
        )
    return result


# ---------- Stats (agrégats pour le tableau de bord) ----------

def _active_streak_dates(db: Session) -> set[date]:
    rows = db.query(models.Streak).filter((models.Streak.sport_fait == 1) | (models.Streak.apprentissage_fait == 1)).all()
    return {r.date for r in rows}


def _current_streak(db: Session) -> int:
    active_dates = _active_streak_dates(db)
    current_streak = 0
    cursor = date.today()
    while cursor in active_dates:
        current_streak += 1
        cursor -= timedelta(days=1)
    return current_streak


@app.get("/api/stats", response_model=schemas.StatsOut)
def get_stats(db: Session = Depends(get_db)):
    total_seances = db.query(models.Seance).filter(models.Seance.statut == "terminee").count()
    total_modules = db.query(models.SessionApprentissage).count()

    rpe_avg = db.query(func.avg(models.Seance.rpe)).filter(models.Seance.rpe.isnot(None)).scalar()

    active_dates = _active_streak_dates(db)
    current_streak = _current_streak(db)

    record_streak = 0
    running = 0
    for d in sorted(active_dates):
        prev = d - timedelta(days=1)
        if prev in active_dates:
            running += 1
        else:
            running = 1
        record_streak = max(record_streak, running)

    xp_total = total_seances * 40 + total_modules * 20

    return schemas.StatsOut(
        streak=current_streak,
        record_streak=max(record_streak, current_streak),
        xp_total=xp_total,
        total_seances=total_seances,
        total_modules=total_modules,
        rpe_average=round(float(rpe_avg), 1) if rpe_avg is not None else 0.0,
    )


# ---------- Progression (graphique de charge + score par thème) ----------

@app.get("/api/progress/charge")
def get_charge_progress(nom_exercice: str = "Développé couché", limit: int = 8, db: Session = Depends(get_db)):
    rows = (
        db.query(models.ExerciceHistorique)
        .filter(models.ExerciceHistorique.nom_exercice == nom_exercice)
        .order_by(models.ExerciceHistorique.date.desc())
        .limit(limit)
        .all()
    )
    rows.reverse()
    return [{"date": r.date.isoformat(), "loadKg": r.charge_kg} for r in rows]


@app.get("/api/progress/themes")
def get_theme_scores(db: Session = Depends(get_db)):
    rows = (
        db.query(
            models.ModuleIntellectuel.categorie,
            func.avg(models.SessionApprentissage.score).label("avg_score"),
        )
        .join(models.SessionApprentissage, models.SessionApprentissage.module_id == models.ModuleIntellectuel.id)
        .group_by(models.ModuleIntellectuel.categorie)
        .all()
    )
    return [{"theme": categorie, "percent": round(float(avg_score), 0)} for categorie, avg_score in rows]
