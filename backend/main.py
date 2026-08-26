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
import moteur_decision
import regles_seance
import schemas
import substitution
import user_model_v2
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

    updates = payload.model_dump(exclude_unset=True)
    if updates.get("statut") == "terminee":
        # Terminer une séance doit passer par /api/seance/terminer, seul endpoint qui calcule
        # le pourcentage de complétion, l'historique et l'XP. Ce PATCH générique ne doit pas
        # permettre de contourner cette logique.
        raise HTTPException(
            status_code=400,
            detail="Utilisez /api/seance/terminer pour terminer une séance.",
        )

    for key, value in updates.items():
        setattr(seance, key, value)
    db.commit()
    db.refresh(seance)
    return seance


# ---------- Remplacement d'exercice (Étape 7C) ----------

MAX_ALTERNATIVES = 5


def _item_pour_exercice(seance: models.Seance, exercice_id: int) -> Optional[dict]:
    for item in seance.exercices or []:
        if isinstance(item, dict) and item.get("exercice_id") == exercice_id:
            return item
    return None


def _materiel_et_zones_pour_seance(seance: models.Seance, db: Session) -> tuple[str, list[str]]:
    """Réutilise le matériel déclaré au profil et les zones sensibles exclues à la
    génération de cette séance (Seance.decision_adaptation["exclusions"], calculées par le
    moteur de règles — voir generer_seance) : le remplacement doit respecter les mêmes
    garde-fous que la génération initiale, pas des garde-fous recalculés différemment."""
    profil = db.query(models.Profil).order_by(models.Profil.id.desc()).first()
    materiel_disponible = profil.materiel if profil else ""
    zones_sensibles = (seance.decision_adaptation or {}).get("exclusions") or []
    return materiel_disponible, zones_sensibles


@app.get(
    "/api/seance/{seance_id}/exercices/{exercice_id}/alternatives",
    response_model=schemas.AlternativesExerciceOut,
)
def get_alternatives_exercice(seance_id: int, exercice_id: int, db: Session = Depends(get_db)):
    seance = db.get(models.Seance, seance_id)
    if not seance:
        raise HTTPException(status_code=404, detail="Séance introuvable")

    if _item_pour_exercice(seance, exercice_id) is None:
        raise HTTPException(status_code=404, detail="Exercice non présent dans cette séance")

    exercice_actuel = db.get(models.ExerciceBibliotheque, exercice_id)
    if not exercice_actuel:
        raise HTTPException(status_code=404, detail="Exercice introuvable")

    bibliotheque = db.query(models.ExerciceBibliotheque).all()
    bibliotheque_par_id = {ex.id: ex for ex in bibliotheque}
    exercice_ids_deja_dans_seance = {
        item.get("exercice_id") for item in (seance.exercices or []) if isinstance(item, dict)
    }
    materiel_disponible, zones_sensibles = _materiel_et_zones_pour_seance(seance, db)

    candidats = substitution.trouver_alternatives(
        substitution.exercice_vers_dict(exercice_actuel),
        [substitution.exercice_vers_dict(ex) for ex in bibliotheque],
        exercice_ids_deja_dans_seance,
        materiel_disponible,
        zones_sensibles,
    )

    alternatives = [
        schemas.AlternativeExerciceOut(
            exercice=schemas.ExerciceBibliothequeOut.model_validate(bibliotheque_par_id[c["exercice"]["id"]]),
            score=c["score"],
            memes_criteres=c["memes_criteres"],
        )
        for c in candidats[:MAX_ALTERNATIVES]
    ]
    return schemas.AlternativesExerciceOut(exercice_actuel_id=exercice_id, alternatives=alternatives)


@app.post("/api/seance/{seance_id}/remplacer_exercice", response_model=schemas.RemplacerExerciceOut)
def remplacer_exercice(seance_id: int, payload: schemas.RemplacerExercicePayload, db: Session = Depends(get_db)):
    seance = db.get(models.Seance, seance_id)
    if not seance:
        raise HTTPException(status_code=404, detail="Séance introuvable")

    if seance.statut == "terminee":
        raise HTTPException(status_code=409, detail="Impossible de remplacer un exercice sur une séance terminée.")

    if payload.exercice_id_actuel == payload.exercice_id_nouveau:
        raise HTTPException(
            status_code=400, detail="L'exercice de remplacement doit être différent de l'exercice actuel."
        )

    exercices = list(seance.exercices or [])
    index_actuel = next(
        (
            i
            for i, item in enumerate(exercices)
            if isinstance(item, dict) and item.get("exercice_id") == payload.exercice_id_actuel
        ),
        None,
    )
    if index_actuel is None:
        raise HTTPException(status_code=404, detail="Exercice non présent dans cette séance")

    autres_ids = {
        item.get("exercice_id")
        for i, item in enumerate(exercices)
        if isinstance(item, dict) and i != index_actuel
    }
    if payload.exercice_id_nouveau in autres_ids:
        raise HTTPException(status_code=409, detail="Cet exercice est déjà présent dans cette séance.")

    exercice_nouveau = db.get(models.ExerciceBibliotheque, payload.exercice_id_nouveau)
    if not exercice_nouveau:
        raise HTTPException(status_code=404, detail="Exercice de remplacement introuvable")
    exercice_actuel = db.get(models.ExerciceBibliotheque, payload.exercice_id_actuel)

    # Ne modifie QUE le slot ciblé : series/repetitions/charge_indicative/notes/rpe_cible/
    # temps_repos_recommande_s sont conservés strictement tels quels (jamais recalculés), seul
    # exercice_id change. historique_exercice_ids trace la chaîne de remplacements (A -> B -> C)
    # pour que terminer_seance() puisse regrouper les séries des anciens exercice_id du slot,
    # sans jamais réécrire les SerieLoggee déjà persistées (vérité historique intacte).
    item_actuel = exercices[index_actuel]
    historique = list(item_actuel.get("historique_exercice_ids") or [])
    if payload.exercice_id_actuel not in historique:
        historique.append(payload.exercice_id_actuel)

    nouvel_item = {**item_actuel, "exercice_id": payload.exercice_id_nouveau, "historique_exercice_ids": historique}
    exercices[index_actuel] = nouvel_item
    seance.exercices = exercices  # réassignation complète : requis pour que SQLAlchemy détecte la mutation d'une colonne JSON
    db.commit()
    db.refresh(seance)

    series_deja_realisees = (
        db.query(models.SerieLoggee)
        .filter(
            models.SerieLoggee.seance_id == seance.id,
            models.SerieLoggee.exercice_id == payload.exercice_id_actuel,
            models.SerieLoggee.coche == 1,
        )
        .count()
    )

    message_confirmation = None
    if series_deja_realisees > 0:
        nom_ancien = exercice_actuel.nom if exercice_actuel else f"Exercice #{payload.exercice_id_actuel}"
        message_confirmation = (
            f"{series_deja_realisees} série(s) déjà réalisée(s) sur {nom_ancien} resteront dans l'historique. "
            f"Les prochaines séries seront réalisées sur {exercice_nouveau.nom}."
        )

    return schemas.RemplacerExerciceOut(
        seance=schemas.SeanceOut.model_validate(seance),
        series_deja_realisees=series_deja_realisees,
        message_confirmation=message_confirmation,
    )


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
    """« Précédent » façon Hevy : les séries cochées de la dernière séance TERMINÉE (autre
    que `seance_id`, la séance en cours) où cet exercice a été loggé. Une séance non
    terminée (encore « planifiee »/« prévue », y compris abandonnée en cours de route)
    n'est jamais éligible comme référence."""
    query = db.query(models.SerieLoggee).filter(
        models.SerieLoggee.exercice_id == exercice_id,
        models.SerieLoggee.coche == 1,
    )
    if seance_id is not None:
        query = query.filter(models.SerieLoggee.seance_id != seance_id)

    derniere_seance_id = (
        query.join(models.Seance, models.Seance.id == models.SerieLoggee.seance_id)
        .filter(models.Seance.statut == "terminee")
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


# Motif strict : un seul nombre suivi (immédiatement ou après espace) de "kg", rien d'autre
# dans la chaîne. Volontairement conservateur : toute formulation contenant plusieurs nombres,
# une unité par élément ("par haltère"), une fourchette ("-", "à") ou du texte descriptif ne
# doit PAS être interprétée au jugé (cf. Étape 4 bis, garde-fou charge) — mieux vaut ne pas
# corriger que corriger sur une fausse lecture (ex: "2 haltères de 10 kg" ≠ 2 kg).
_CHARGE_NUMERIQUE_STRICTE_RE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*kg\s*$", re.IGNORECASE)


def _charge_prevue_depuis_indicative(charge_indicative: Optional[str]) -> Optional[float]:
    if not charge_indicative or re.search(r"corps", charge_indicative, re.IGNORECASE):
        return None
    m = _CHARGE_NUMERIQUE_STRICTE_RE.match(charge_indicative)
    return float(m.group(1).replace(",", ".")) if m else None


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
#
# Pas de POST ici : les entrées sont créées uniquement côté serveur par terminer_seance()
# (aucun consommateur frontend n'appelait l'ancien POST /api/historique_seances, qui aurait
# permis d'écrire une entrée arbitraire — chemin client-writable retiré).


def _enrichir_noms_exercices_prevus(exercices_prevus: list[dict], db: Session) -> list[dict]:
    """exercices_prevus (copie brute de Seance.exercices) ne contient que exercice_id, pas de
    nom : on résout les noms via la bibliothèque pour l'affichage, sans toucher aux données
    persistées ni au format existant du champ."""
    ids = {item.get("exercice_id") for item in exercices_prevus if isinstance(item, dict) and item.get("exercice_id") is not None}
    if not ids:
        return exercices_prevus
    noms_par_id = {
        ex.id: ex.nom for ex in db.query(models.ExerciceBibliotheque).filter(models.ExerciceBibliotheque.id.in_(ids)).all()
    }
    return [
        {**item, "nom": noms_par_id.get(item.get("exercice_id"))} if isinstance(item, dict) else item
        for item in exercices_prevus
    ]


@app.get("/api/historique_seances", response_model=list[schemas.HistoriqueSeanceOut])
def list_historique_seances(db: Session = Depends(get_db)):
    entries = db.query(models.HistoriqueSeance).order_by(models.HistoriqueSeance.date.desc()).all()
    for entry in entries:
        entry.exercices_prevus = _enrichir_noms_exercices_prevus(entry.exercices_prevus or [], db)
    return entries


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


# Valeurs contrôlées pour TerminerSeancePayload.zone_sensible, exactement les groupes musculaires
# utilisés par regles_seance.GROUPES_PAR_TYPE_SEANCE (union de toutes les valeurs de cette table) :
# réutiliser d'autres libellés casserait le matching de appliquer_garde_fous/
# substitution.groupe_concerne_par_zone_sensible, qui comparent par égalité de chaîne (insensible
# à la casse).
ZONES_SENSIBLES_VALIDES = ["jambes", "dos", "épaules", "bras", "mollets", "abdos"]


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
        if substitution.groupe_concerne_par_zone_sensible(ex.groupe_musculaire, zones_sensibles):
            return False
        if not substitution.materiel_compatible(ex.materiel_requis, materiel_disponible):
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
    plan: list[dict],
    type_seance_suggere: str,
    rpe_cible: int,
    charges_cibles: Optional[dict[int, float]] = None,
    charges_depart: Optional[dict[int, float]] = None,
) -> dict:
    """Séance de repli, construite sans IA à partir du plan déjà calibré en temps, utilisée
    quand Mistral échoue à renvoyer des exercice_id valides après une nouvelle tentative.

    charges_cibles (voir _construire_charges_cibles, même source de vérité que le garde-fou
    appliqué au chemin Mistral, calculée une seule fois par generer_seance et simplement
    transmise ici) : quand un historique réel existe pour un exercice non poids_du_corps, la
    charge cible déterministe est utilisée directement au lieu du texte générique "à ajuster
    selon ressenti".

    charges_depart (voir _construire_charges_depart, même source de vérité que celle injectée
    dans le prompt Mistral, calculée une seule fois par generer_seance et simplement transmise
    ici) : à défaut d'historique réel, sert de repli avant le texte générique — jamais
    d'ajustement_charge_pct appliqué dessus (charges_depart est une estimation poids du corps
    sans référence réelle, pas une progression)."""
    charges_cibles = charges_cibles or {}
    charges_depart = charges_depart or {}
    autres = [p for p in plan if p["exercice"].type != "gainage_prevention"][:4]
    gainage = next((p for p in plan if p["exercice"].type == "gainage_prevention"), None)

    choisis = autres or list(plan)[:4]
    if gainage and gainage not in choisis:
        choisis.append(gainage)

    def _charge_indicative_secours(p: dict) -> str:
        if p["exercice"].charge_recommandee == "poids_du_corps":
            return "poids du corps"
        cible = charges_cibles.get(p["exercice"].id)
        if cible is not None:
            return f"{cible:g} kg"
        depart = charges_depart.get(p["exercice"].id)
        if depart is not None:
            return f"{depart:g} kg (estimation de départ)"
        return "à ajuster selon ressenti"

    exercices = [
        {
            "exercice_id": p["exercice"].id,
            "series": p["series"],
            "repetitions": "10-12",
            "charge_indicative": _charge_indicative_secours(p),
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


TOLERANCE_CHARGE_RELATIVE = 0.075  # 7.5% de la charge cible
TOLERANCE_CHARGE_MIN_KG = 2.5  # absorbe l'arrondi aux disques de 2.5kg (voir charge_depart.py)


def _derniere_charge_reelle(exercice_id: int, db: Session) -> Optional[float]:
    """MAX des poids_kg des séries cochées de la dernière séance (par date, puis id en
    tie-break) où cet exercice a réellement été effectué, ou None si aucun historique réel
    n'existe pour cet exercice.

    Le MAX (et non la moyenne) représente la meilleure charge de travail réellement validée
    ce jour-là : une moyenne mélange à tort échauffement, top set et éventuel drop set, ce qui
    fait dériver la référence vers le bas et fausse le garde-fou (ex: 40/60/70/80 kg -> une
    moyenne à 62.5kg sous-estime largement ce que le joueur a réellement soulevé, alors que la
    référence pertinente pour la séance suivante est 80kg)."""
    derniere = (
        db.query(models.SerieLoggee.seance_id)
        .join(models.Seance, models.Seance.id == models.SerieLoggee.seance_id)
        .filter(
            models.SerieLoggee.exercice_id == exercice_id,
            models.SerieLoggee.coche == 1,
            models.SerieLoggee.poids_kg.isnot(None),
        )
        .order_by(models.Seance.date.desc(), models.SerieLoggee.id.desc())
        .first()
    )
    if derniere is None:
        return None

    poids = [
        row[0]
        for row in db.query(models.SerieLoggee.poids_kg)
        .filter(
            models.SerieLoggee.seance_id == derniere[0],
            models.SerieLoggee.exercice_id == exercice_id,
            models.SerieLoggee.coche == 1,
            models.SerieLoggee.poids_kg.isnot(None),
        )
        .all()
    ]
    if not poids:
        return None
    return max(poids)


def _arrondir_charge_cible(cible: float, charge_recommandee: str) -> float:
    """Arrondit la charge cible selon la granularité pertinente pour le type de charge —
    pas de plancher universel à 2.5kg : ce plancher n'a de sens que pour les charges
    barbell/lourdes (disques de 2.5kg), pas pour une charge légère (haltères fins,
    élastiques...) où il transformerait artificiellement une petite charge légitime
    (1kg, 3kg) en charge supérieure injustifiée."""
    if charge_recommandee == "charge_legere":
        # Granularité fine (0.5kg), sans plancher artificiel : une charge légère proche de 0
        # reste proche de 0.
        return max(round(cible * 2) / 2, 0.5)
    # charge_moderee / charge_lourde_progressive (et tout autre cas non prévu) : granularité
    # 2.5kg, comportement historique conservé.
    return max(round(cible / 2.5) * 2.5, 2.5)


def _construire_charges_cibles(
    plan: list[dict],
    ajustement_charge_pct: float,
    db: Session,
) -> dict[int, float]:
    """Calcule, pour chaque exercice du plan disposant d'un historique réel loggé
    (voir _derniere_charge_reelle) et non marqué poids_du_corps, la charge cible (kg)
    issue de l'ajustement décidé par regles_seance.py. Les exercices sans historique
    comparable (jamais loggés) sont absents du résultat : aucune charge n'est forcée
    dessus, faute de référence fiable."""
    cibles: dict[int, float] = {}
    for p in plan:
        ex = p["exercice"]
        if ex.charge_recommandee == "poids_du_corps":
            continue
        reference = _derniere_charge_reelle(ex.id, db)
        if reference is None:
            continue
        cible = reference * (1 + ajustement_charge_pct / 100)
        cibles[ex.id] = _arrondir_charge_cible(cible, ex.charge_recommandee)
    return cibles


def _corriger_charges_hors_tolerance(exercices: list[dict], charges_cibles: dict[int, float]) -> None:
    """Garde-fou post-génération : le backend reste l'autorité finale sur la charge quand un
    historique réel existe. Pour chaque exercice ayant une charge cible calculée (voir
    _construire_charges_cibles), force charge_indicative à la cible si Mistral a renvoyé une
    valeur numérique claire et hors tolérance — sinon laisse la valeur de Mistral inchangée
    (variations légitimes dans la tolérance).

    Une valeur ambiguë ou non interprétable (ex: "2 haltères de 10 kg", "20-22 kg", "charge
    modérée") n'est PAS corrigée : non parsable/ambigu ne veut pas dire que Mistral a tort, et
    le garde-fou ne doit jamais deviner une charge à partir d'une formulation incertaine (voir
    _charge_prevue_depuis_indicative)."""
    for item in exercices:
        cible = charges_cibles.get(item.get("exercice_id"))
        if cible is None:
            continue
        actuelle = _charge_prevue_depuis_indicative(item.get("charge_indicative"))
        if actuelle is None:
            continue
        tolerance = max(TOLERANCE_CHARGE_MIN_KG, cible * TOLERANCE_CHARGE_RELATIVE)
        if abs(actuelle - cible) <= tolerance:
            continue
        ancienne = item.get("charge_indicative")
        item["charge_indicative"] = f"{cible:g} kg"
        logger.warning(
            "Charge hors tolérance pour exercice %s : Mistral a renvoyé %r, cible calculée "
            "%.1fkg (tolérance ±%.1fkg) -> corrigée à %.1fkg.",
            item.get("exercice_id"),
            ancienne,
            cible,
            tolerance,
            cible,
        )


def _appliquer_calibrage_temps(exercices: list[dict], plan: list[dict], rpe_cible: int) -> None:
    """Garde-fou post-génération : impose series / temps_repos_recommande_s à partir du plan
    calculé côté serveur (duree_seance.calibrer_exercices) et plafonne rpe_cible à rpe_cible
    (dérivé de intensite_max par regles_seance/duree_seance.rpe_cible_pour_intensite — le
    moteur de règles reste la seule source de vérité, cette fonction ne fait qu'appliquer son
    plafond), plutôt que de laisser Mistral décider seul du respect du temps disponible et de
    l'intensité max. Un rpe_cible absent/non entier reprend directement le plafond ; un rpe_cible
    inférieur ou égal au plafond est laissé inchangé ; seul un dépassement est corrigé."""
    plan_par_id = {item["exercice"].id: item for item in plan}
    for item in exercices:
        p = plan_par_id.get(item.get("exercice_id"))
        if p is None:
            continue
        item["series"] = p["series"]
        item["temps_repos_recommande_s"] = p["temps_repos_recommande_s"]
        if not isinstance(item.get("rpe_cible"), int) or item["rpe_cible"] > rpe_cible:
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


def _intitule_coach(sport: Optional[str]) -> str:
    """Phase 6 : plus de hardcoding football — le rôle du coach dépend de
    contexte_sportif.sport (générique si absent, sans injecter de contexte football)."""
    if sport == "football":
        return "un coach sportif spécialisé en préparation physique football"
    if sport:
        return f"un coach sportif de préparation physique pour un pratiquant de {sport}"
    return "un coach sportif de préparation physique générique"


def _construire_system_prompt(sport: Optional[str] = None) -> str:
    notes = connaissances.get_notes_generation_ia()
    notes_txt = "\n".join(f"- {n}" for n in notes)
    return (
        f"Tu es {_intitule_coach(sport)}. "
        "Règles de comportement à respecter systématiquement, sans exception :\n"
        f"{notes_txt}\n"
        "- Pour chaque exercice, respecte strictement le champ charge_recommandee fourni. "
        "Ne propose jamais de charge lourde sur un exercice marqué poids_du_corps ou "
        "charge_legere, même si l'utilisateur a un bon niveau de force déclaré — la nature "
        "de l'exercice prime sur le niveau de l'utilisateur.\n"
        "- Les objectifs du joueur te sont fournis déjà hiérarchisés (rang + poids) : ne "
        "devine jamais un objectif principal différent, ne réordonne pas les priorités."
    )


def _construire_prompt_generation(
    profil: dict,
    recommandation: dict,
    etat_du_jour: dict,
    plan: list[dict],
    fiches_theoriques: list[str],
    charges_depart: Optional[dict[int, float]] = None,
    rpe_cible: int = duree_seance.RPE_CIBLE_DEFAUT,
    decision: Optional["moteur_decision.DecisionCoaching"] = None,
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

    sport = (profil.get("contexte_sportif") or {}).get("sport")
    intitule_joueur = "un pratiquant de football amateur" if sport == "football" else (
        f"un pratiquant de {sport} amateur" if sport else "un pratiquant"
    )
    objectifs_v2 = profil.get("objectifs_v2") or []
    objectifs_txt = (
        "; ".join(f"{o['theme']} (rang {o['rang']}, poids {o['poids']})" for o in objectifs_v2)
        if objectifs_v2 else "aucun objectif déclaré"
    )
    niveau_effectif = profil.get("_niveau_effectif")

    strategie_txt = ""
    if decision is not None:
        strategie_txt = "\n\n" + moteur_decision.formater_section_prompt(decision)

    return f"""Tu es un coach sportif qui construit une séance de sport concrète pour {intitule_joueur}.
{strategie_txt}

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
- Sport pratiqué : {sport or 'non renseigné'}
- Poste : {profil.get('poste') or 'non applicable'}
- Objectifs déclarés, déjà hiérarchisés (backend a déjà déterminé la priorité — ne pas réordonner
  ni deviner un autre objectif principal) : {objectifs_txt}
- Niveau physique global (effectif, calibré déclaré/observé) : {niveau_effectif if niveau_effectif is not None else profil.get('niveau_physique')}
- Qualités physiques déclarées (1 à 5) : {profil.get('niveaux_qualites_physiques')}
- Matériel disponible : {profil.get('materiel')}

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
    series_cible = duree_seance.series_cible_depuis_ajustement(recommandation.get("ajustement_volume_pct"))
    plan = duree_seance.calibrer_exercices(candidats, temps_dispo_min, series_cible)
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
    # Phase 5/7 : Mistral reçoit le niveau effectif (déclaré recalibré par l'observé selon la
    # confiance) plutôt que le déclaré brut, quand un niveau observé existe déjà.
    profil_dict["_niveau_effectif"] = _niveau_physique_effectif(profil, profil_dict)

    # Moteur de décision déterministe (User Model V2 -> stratégie de coaching) : purement
    # additif, ne doit jamais empêcher la génération de séance existante en cas de souci.
    decision: Optional[moteur_decision.DecisionCoaching] = None
    try:
        decision = moteur_decision.construire_decision(
            profil_dict,
            historique_ctx,
            etat_du_jour,
            type_seance_gabarit=type_seance_gabarit,
            aujourdhui=today,
            niveau_effectif=profil_dict["_niveau_effectif"],
        )
    except Exception:
        logger.exception("Moteur de décision indisponible : génération de séance sans section stratégie.")
        decision = None

    system_prompt = _construire_system_prompt(sport=(profil_dict.get("contexte_sportif") or {}).get("sport"))
    prompt = _construire_prompt_generation(
        profil_dict, recommandation, etat_du_jour, plan, fiches_theoriques, charges_depart, rpe_cible, decision
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

    # Calculée une seule fois, avant de savoir si on utilisera Mistral ou le secours : même
    # source de vérité pour les deux chemins (voir _construire_seance_secours et
    # _corriger_charges_hors_tolerance), aucun calcul dupliqué.
    charges_cibles = _construire_charges_cibles(plan, recommandation.get("ajustement_charge_pct", 0.0), db)

    if data is None:
        logger.error("Génération de séance IA impossible après retentative : repli sur une séance de secours.")
        data = _construire_seance_secours(
            plan, recommandation["type_seance_suggere"], rpe_cible, charges_cibles, charges_depart
        )

    # Capture de l'état pré-correction pour détecter ce que le garde-fou Étape 4 corrige
    # réellement (voir _corriger_charges_hors_tolerance, non modifiée), sans dupliquer sa logique.
    charge_indicative_avant = {
        item.get("exercice_id"): item.get("charge_indicative") for item in data["exercices"] if isinstance(item, dict)
    }
    _corriger_charges_hors_tolerance(data["exercices"], charges_cibles)
    corrections_charge = [
        {
            "exercice_id": item.get("exercice_id"),
            "valeur_proposee": charge_indicative_avant.get(item.get("exercice_id")),
            "valeur_appliquee": item.get("charge_indicative"),
        }
        for item in data["exercices"]
        if isinstance(item, dict) and item.get("charge_indicative") != charge_indicative_avant.get(item.get("exercice_id"))
    ]

    duree_calibree_min = duree_seance.duree_totale_estimee_min(plan)

    # Décision réellement appliquée à cette séance : la recommandation calculée par le moteur
    # de règles, plus les valeurs déterministes qui en découlent (série/rpe cibles, charges
    # cibles) et les corrections effectivement effectuées par le garde-fou Étape 4 — pas
    # simplement la reco théorique envoyée à Mistral. Volontairement pas de dump complet de la
    # réponse Mistral (transparence utile, pas de données superflues).
    decision_adaptation = {
        "ajustement_charge_pct": recommandation.get("ajustement_charge_pct"),
        "ajustement_volume_pct": recommandation.get("ajustement_volume_pct"),
        "intensite_max": recommandation.get("intensite_max"),
        "exclusions": recommandation.get("exclusions") or [],
        "raisons": recommandation.get("raisons") or [],
        "series_cible": series_cible,
        "rpe_cible": rpe_cible,
        "charges_cibles": {str(k): v for k, v in charges_cibles.items()},
        "correction_charge_appliquee": bool(corrections_charge),
        "corrections_charge": corrections_charge,
    }

    seance = models.Seance(
        date=today,
        nom=data["nom_seance"],
        exercices=data["exercices"],
        statut="prévue",
        type_seance=recommandation["type_seance_suggere"],
        explication=data.get("explication"),
        duree_prevue=duree_calibree_min,
        duree_reelle=None,
        etat_declare_avant=schemas.EtatDeclareAvant(**etat_du_jour).model_dump(),
        decision_adaptation=decision_adaptation,
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


# ---------- Niveau déclaré / observé / effectif (Phase 5) ----------

# Mapping conservateur type_seance -> qualité(s) physiques concernées, utilisé pour ne
# recalculer le niveau observé d'une qualité qu'à partir de séances réellement pertinentes
# pour elle (voir user_model_v2.calculer_niveau_observe : n'invente jamais une mesure).
TYPE_SEANCE_VERS_QUALITES: dict[str, list[str]] = {
    "force": ["force"],
    "explosivité_vitesse": ["explosivite", "vitesse"],
    "endurance": ["endurance"],
}


def _recalculer_niveau_observe(db: Session, utilisateur_id: Optional[int]) -> dict:
    """Recalcule (mémoire, non persisté ici) le niveau observé par qualité à partir de
    HistoriqueSeance. Reste conservateur : une qualité sans séance pertinente n'a pas
    d'entrée (voir user_model_v2.calculer_niveau_observe -> None)."""
    historiques = db.query(models.HistoriqueSeance).order_by(models.HistoriqueSeance.date.asc()).all()
    resultat: dict[str, dict] = {}
    for qualite in user_model_v2.QUALITES_PHYSIQUES:
        seances_pertinentes = [
            {"rpe": h.rpe, "pourcentage_complete": h.pourcentage_complete}
            for h in historiques
            if qualite in TYPE_SEANCE_VERS_QUALITES.get(h.type_seance, [])
        ]
        valeur = user_model_v2.calculer_niveau_observe(seances_pertinentes)
        confiance = user_model_v2.calculer_confiance(len(seances_pertinentes))
        resultat[qualite] = {"valeur": valeur, "confiance": confiance, "n_seances": len(seances_pertinentes)}
    return resultat


def _niveau_physique_effectif(profil: models.Profil, profil_dict: dict) -> dict[str, float]:
    """Niveau effectif par qualité (voir user_model_v2.calculer_niveau_effectif), à partir du
    niveau déclaré (niveaux_qualites_physiques, 1-5) et du dernier niveau observé persisté sur
    le profil (calculé et écrit par terminer_seance -> _mettre_a_jour_niveau_observe)."""
    declare = profil_dict.get("niveaux_qualites_physiques") or {}
    observe = (getattr(profil, "niveau_observe", None) or {}) if profil else {}
    effectif: dict[str, float] = {}
    for qualite in user_model_v2.QUALITES_PHYSIQUES:
        niveau_declare = declare.get(qualite)
        if niveau_declare is None:
            continue
        info_observe = observe.get(qualite) or {}
        effectif[qualite] = user_model_v2.calculer_niveau_effectif(
            float(niveau_declare), info_observe.get("valeur"), info_observe.get("confiance") or 0.0
        )
    return effectif


# Seuil de variation (échelle 1-5) au-delà duquel un changement de niveau effectif est jugé
# "significatif" et déclenche une entrée NiveauHistorique — évite de journaliser un bruit de
# +/-0.1 après chaque séance tout en restant réactif à une vraie évolution.
SEUIL_VARIATION_NIVEAU_HISTORIQUE = 0.5


def _mettre_a_jour_niveau_observe(db: Session, profil: models.Profil, today: date) -> None:
    """Recalcule le niveau observé, le persiste sur le profil, et journalise dans
    NiveauHistorique toute évolution significative du niveau effectif résultant (Phase 5)."""
    ancien_effectif = _niveau_physique_effectif(
        profil, schemas.ProfilOut.model_validate(profil).model_dump(mode="json")
    )

    nouveau_observe = _recalculer_niveau_observe(db, profil.id)
    profil.niveau_observe = nouveau_observe
    db.commit()
    db.refresh(profil)

    nouveau_effectif = _niveau_physique_effectif(
        profil, schemas.ProfilOut.model_validate(profil).model_dump(mode="json")
    )

    for qualite in user_model_v2.QUALITES_PHYSIQUES:
        avant = ancien_effectif.get(qualite)
        apres = nouveau_effectif.get(qualite)
        if avant is None or apres is None:
            continue
        if abs(apres - avant) < SEUIL_VARIATION_NIVEAU_HISTORIQUE:
            continue
        n_seances = (nouveau_observe.get(qualite) or {}).get("n_seances", 0)
        db.add(
            models.NiveauHistorique(
                utilisateur_id=profil.id,
                qualite=qualite,
                ancien_niveau=round(avant),
                nouveau_niveau=round(apres),
                date=today,
                critere_declencheur=(
                    f"niveau effectif recalculé après {n_seances} séance(s) comparable(s) "
                    f"(observé={((nouveau_observe.get(qualite) or {}).get('valeur'))}, "
                    f"confiance={((nouveau_observe.get(qualite) or {}).get('confiance'))})"
                ),
            )
        )
    db.commit()


@app.get("/api/niveau/historique", response_model=list[schemas.NiveauHistoriqueOut])
def get_niveau_historique(db: Session = Depends(get_db)):
    """Lecture de l'historique des évolutions de niveau (Phase 5) : traçabilité
    ancien/nouveau niveau + raison, la plus récente en premier."""
    return db.query(models.NiveauHistorique).order_by(models.NiveauHistorique.date.desc(), models.NiveauHistorique.id.desc()).all()


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

    exercices_seance = [item for item in (seance.exercices or []) if isinstance(item, dict)]

    # Union des exercice_id à résoudre en bibliothèque : ceux des séries validées (pour le nom
    # d'un exercice remplacé qui n'est plus dans Seance.exercices, filet de sécurité ci-dessous)
    # et ceux des slots actuels (pour le nom courant de chaque slot, même sans série validée dessus).
    exercices_ids = sorted(
        {s.exercice_id for s in series_validees}
        | {item.get("exercice_id") for item in exercices_seance if item.get("exercice_id") is not None}
    )
    bibliotheque_par_id = {
        ex.id: ex for ex in db.query(models.ExerciceBibliotheque).filter(models.ExerciceBibliotheque.id.in_(exercices_ids)).all()
    } if exercices_ids else {}

    # Regroupement par « slot » de Seance.exercices plutôt que par exercice_id brut : après un
    # remplacement (Étape 7C, voir /api/seance/{id}/remplacer_exercice), les séries déjà validées
    # sur l'ancien exercice restent en base avec l'ancien exercice_id (jamais réécrites), mais
    # doivent apparaître dans le même résumé que les séries du nouvel exercice — c'est
    # historique_exercice_ids qui porte la trace de cette chaîne (A -> B -> C).
    exercices_realises = []
    exercice_ids_couverts: set[int] = set()
    for item in exercices_seance:
        exercice_id_actuel = item.get("exercice_id")
        slot_ids = {exercice_id_actuel} | set(item.get("historique_exercice_ids") or [])
        series_slot = sorted(
            (s for s in series_validees if s.exercice_id in slot_ids),
            key=lambda s: (s.horodatage is None, s.horodatage, s.numero_serie),
        )
        if not series_slot:
            continue
        exercice_ids_couverts |= slot_ids
        exercice_courant = bibliotheque_par_id.get(exercice_id_actuel)
        exercices_realises.append(
            {
                "exercice_id": exercice_id_actuel,
                "nom": exercice_courant.nom if exercice_courant else None,
                "historique_exercice_ids": item.get("historique_exercice_ids") or [],
                "series": [
                    {
                        "numero_serie": s.numero_serie,
                        "poids_kg": s.poids_kg,
                        "repetitions": s.repetitions,
                        "exercice_id": s.exercice_id,
                    }
                    for s in series_slot
                ],
            }
        )

    # Filet de sécurité : séries validées sur un exercice qui n'appartient à aucun slot actuel
    # (ne devrait pas arriver via remplacer_exercice, qui conserve toujours l'ancien id dans
    # historique_exercice_ids, mais couvre tout autre cas) — un groupe par exercice_id restant,
    # comportement identique à avant l'Étape 7C.
    for exercice_id in sorted({s.exercice_id for s in series_validees} - exercice_ids_couverts):
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
        # Valeur contrôlée (voir ZONES_SENSIBLES_VALIDES) déclarée en fin de séance par le
        # joueur ; toute valeur hors liste (ex: "Aucune" côté frontend, ou une valeur invalide)
        # est traitée comme "pas de zone sensible" plutôt que d'être enregistrée telle quelle.
        zone_sensible_signalee=payload.zone_sensible if payload.zone_sensible in ZONES_SENSIBLES_VALIDES else None,
        xp_gagne=xp_gagne,
        notes=payload.note,
        # Reportés tels quels depuis la Seance liée (capturés à la génération, cf.
        # generer_seance) : lien direct via l'objet déjà chargé plus haut, jamais de
        # récupération fragile par date/dernier historique. Séances générées avant
        # l'introduction de ces colonnes -> None/absent, donc {} ici, sans rien inventer.
        etat_declare_avant=seance.etat_declare_avant or {},
        decision_adaptation=seance.decision_adaptation,
    )
    db.add(historique)
    db.commit()
    db.refresh(historique)

    if profil is not None:
        # Phase 5/9 : ne doit jamais faire échouer la fin de séance si le recalcul du
        # niveau observé rencontre un cas inattendu (ex: profil legacy) — best effort.
        try:
            _mettre_a_jour_niveau_observe(db, profil, seance.date)
        except Exception:
            logger.exception("Échec du recalcul du niveau observé après terminer_seance (non bloquant)")

    return schemas.TerminerSeanceOut(resume=resume, xp_gagne=xp_gagne, historique_id=historique.id)


# ---------- Programme structuré (8 semaines, indépendant de /api/seance/generer) ----------

DUREE_SEMAINES_PROGRAMME_DEFAUT = 8


# TYPES_SEANCE_PROGRAMME / _normaliser_type_seance_programme vivent désormais dans
# moteur_decision.py (réutilisés par la validation post-Mistral, elle-même déplacée là-bas —
# une seule source de vérité pour la taxonomie des types de séance du programme).
TYPES_SEANCE_PROGRAMME = moteur_decision.TYPES_SEANCE_PROGRAMME
_normaliser_type_seance_programme = moteur_decision.normaliser_type_seance_programme


def _construire_system_prompt_programme(sport: Optional[str] = None) -> str:
    return (
        f"Tu es {_intitule_coach(sport)} qui construit un programme "
        "structuré sur plusieurs semaines. Règles impératives :\n"
        "- La répartition hebdomadaire (quels jours, quels types de séance, présence ou absence "
        "de séance) t'est fournie ci-dessous comme une DÉCISION STRUCTURELLE DU COACH déjà prise "
        "par un moteur déterministe, à partir des objectifs hiérarchisés du joueur et de son "
        "calendrier de matchs. Tu ne la redéfinis pas, tu ne la réinterprètes pas : tu génères "
        "uniquement les détails de contenu (exercices, séries, répétitions, durée, progression, "
        "phase, récupération) pour chaque jour tel qu'imposé.\n"
        "- La progression de charge/volume doit être prudente et réaliste : jamais plus de "
        "5 à 8% de progression cumulée par semaine."
    )


def _construire_prompt_programme(
    profil: dict, fiches_theoriques: list[str], jours_dispo: list[str], structure_hebdomadaire: dict
) -> str:
    fiches_txt = "\n\n".join(fiches_theoriques) if fiches_theoriques else "aucune"
    jour_match = (profil.get("calendrier_matchs") or {}).get("jour_habituel") or "non renseigné"
    sport = (profil.get("contexte_sportif") or {}).get("sport")
    intitule_joueur = "un joueur de football amateur" if sport == "football" else (
        f"un pratiquant de {sport} amateur" if sport else "un pratiquant"
    )
    objectifs_v2 = profil.get("objectifs_v2") or []
    objectifs_txt = (
        "; ".join(f"{o['theme']} (rang {o['rang']}, poids {o['poids']})" for o in objectifs_v2)
        if objectifs_v2 else (profil.get("objectifs") or [])
    )
    structure_txt = moteur_decision.formater_structure_hebdomadaire_prompt(structure_hebdomadaire)

    return f"""Construis un programme d'entraînement physique structuré sur {DUREE_SEMAINES_PROGRAMME_DEFAUT} semaines
pour {intitule_joueur}, à partir de son profil complet.

{structure_txt}

PROFIL (pour contexte uniquement — la répartition hebdomadaire ci-dessus est déjà tranchée)
- Objectifs déclarés, déjà hiérarchisés : {objectifs_txt}
- Sport pratiqué : {sport or 'non renseigné'}
- Poste : {profil.get('poste') or 'non applicable'}
- Niveau physique global : {profil.get('niveau_physique')}
- Qualités physiques déclarées (1 à 5) : {profil.get('niveaux_qualites_physiques')}
- Jour de match habituel : {jour_match}
- Entraînements club : {(profil.get('calendrier_matchs') or {}).get('entrainements_club')}
- Jours disponibles déclarés : {jours_dispo}
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
  "gabarit_hebdomadaire": {{"<jour parmi {list(structure_hebdomadaire.keys())}>": "<type IMPOSÉ ci-dessus, recopié tel quel>", "...": "..."}},
  "trajectoire_progression": {{
    "force": [8 nombres, progression en % relatif à la semaine 1 (100 = point de départ)],
    "explosivite": [8 nombres, même logique],
    "esthetique": [8 nombres, même logique],
    "endurance": [8 nombres, même logique — inclus seulement si au moins un jour de la structure imposée est de type "endurance"]
  }}
}}

Le gabarit_hebdomadaire doit reprendre EXACTEMENT les jours et les types de la décision structurelle
ci-dessus (ni jour ni type ajouté, modifié ou supprimé). La trajectoire_progression doit contenir
exactement {DUREE_SEMAINES_PROGRAMME_DEFAUT} valeurs par qualité, en progression prudente (jamais plus
de 5 à 8% cumulés par semaine)."""


# _programme_depuis_structure / _construire_programme_secours / _valider_gabarit_contre_structure
# vivent désormais dans moteur_decision.py (fonctions pures, testables sans FastAPI/SQLAlchemy —
# voir backend/test_structure_hebdomadaire.py) : main.py se contente de les appeler, pour ne
# jamais dupliquer la logique de structure/validation dans deux modules (spécification P1.0
# section 14/19 : une seule source de vérité).
_construire_programme_secours = moteur_decision.construire_programme_secours
_valider_gabarit_contre_structure = moteur_decision.valider_gabarit_contre_structure


@app.post("/api/programme/generer", response_model=schemas.ProgrammeOut)
def generer_programme(payload: schemas.ProgrammeGenererPayload, db: Session = Depends(get_db)):
    profil = db.query(models.Profil).order_by(models.Profil.id.desc()).first()
    if not profil:
        raise HTTPException(status_code=400, detail="Aucun profil enregistré : termine l'onboarding avant de générer un programme.")

    utilisateur_id = payload.utilisateur_id if payload.utilisateur_id is not None else profil.id
    profil_dict = schemas.ProfilOut.model_validate(profil).model_dump(mode="json")

    # Phase 3 : lecture directe du dict structuré `disponibilites`, plus de parsing fragile
    # de contraintes_temps (conservé uniquement comme fallback via ProfilBase, déjà appliqué
    # à l'écriture — profil_dict.disponibilites est donc toujours structuré ici).
    disponibilites = profil_dict.get("disponibilites") or {}
    jours_dispo = user_model_v2.jours_dispo_abbrev(disponibilites)

    contexte_sportif = profil_dict.get("contexte_sportif") or {}
    sport = contexte_sportif.get("sport")

    # P1.0 : USER MODEL -> MOTEUR DÉTERMINISTE -> STRUCTURE HEBDOMADAIRE CONTRAIGNANTE -> Mistral.
    # C'est cette structure (et elle seule) qui arbitre jours/types ; Mistral ne fait que détailler
    # le contenu autour d'elle (voir _construire_prompt_programme et la validation post-Mistral
    # ci-dessous). Même fonction utilisée par le fallback (_construire_programme_secours).
    structure_hebdomadaire = moteur_decision.construire_structure_hebdomadaire(
        objectifs_v2=profil_dict.get("objectifs_v2"),
        sport=sport,
        poste=profil_dict.get("poste"),
        disponibilites=disponibilites,
        jour_match_habituel=(profil_dict.get("calendrier_matchs") or {}).get("jour_habituel"),
        frequence_hebdo=contexte_sportif.get("frequence_hebdo"),
        objectifs_legacy=profil_dict.get("objectifs"),
    )

    fiches_theoriques = connaissances.selectionner_fiches_programme(profil_dict.get("poste"))
    system_prompt = _construire_system_prompt_programme(sport=sport)
    prompt = _construire_prompt_programme(profil_dict, fiches_theoriques, jours_dispo, structure_hebdomadaire)

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

        gabarit_brut = reponse.get("gabarit_hebdomadaire")
        if not isinstance(gabarit_brut, dict) or not gabarit_brut:
            logger.warning("gabarit_hebdomadaire absent ou vide pour le programme (tentative %s) : %s", tentative + 1, reponse)
            continue

        # Validation déterministe post-Mistral (spécification section 13) : la structure
        # hebdomadaire imposée est la seule source de vérité sur les jours/types. Si Mistral
        # dévie (split générique, jour ajouté/supprimé, type changé), on applique l'option A
        # (préférée) : les types déterministes attendus remplacent ceux retournés — jamais un
        # gabarit incohérent avec la décision structurelle n'est enregistré en DB.
        gabarit_normalise, conforme = _valider_gabarit_contre_structure(gabarit_brut, structure_hebdomadaire)
        if not conforme:
            logger.warning(
                "gabarit_hebdomadaire Mistral non conforme à la structure déterministe (tentative %s) : "
                "reçu=%r attendu=%r — types corrigés pour respecter la décision du coach.",
                tentative + 1, gabarit_brut, gabarit_normalise,
            )

        reponse["gabarit_hebdomadaire"] = gabarit_normalise
        data = reponse
        break

    if data is None:
        logger.error("Génération de programme IA impossible après retentative : repli sur un programme de secours.")
        data = _construire_programme_secours(structure_hebdomadaire)

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
    """Charge la plus lourde validée par séance pour l'exercice donné, à partir des vraies
    séries loguées (series_loggees) — plus fiable que exercices_historique, une table legacy
    que plus rien n'alimente depuis que le logging passe par SerieLoggee (voir Étape 1)."""
    exercice = db.query(models.ExerciceBibliotheque).filter(models.ExerciceBibliotheque.nom == nom_exercice).first()
    if not exercice:
        return []

    rows = (
        db.query(models.SerieLoggee.poids_kg, models.Seance.date)
        .join(models.Seance, models.Seance.id == models.SerieLoggee.seance_id)
        .filter(
            models.SerieLoggee.exercice_id == exercice.id,
            models.SerieLoggee.coche == 1,
            models.SerieLoggee.poids_kg.isnot(None),
        )
        .all()
    )

    charge_max_par_date: dict = {}
    for poids_kg, seance_date in rows:
        charge_max_par_date[seance_date] = max(charge_max_par_date.get(seance_date, 0), poids_kg)

    dates_retenues = sorted(charge_max_par_date.keys())[-limit:]
    return [{"date": d.isoformat(), "loadKg": charge_max_par_date[d]} for d in dates_retenues]


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
