import os
from datetime import date, timedelta
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
import schemas
from calendrier import compute_phase
from database import Base, SessionLocal, engine, get_db
from seed import seed

Base.metadata.create_all(bind=engine)

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
def get_today_seance(db: Session = Depends(get_db)):
    return db.query(models.Seance).filter(models.Seance.date == date.today()).first()


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

@app.get("/api/stats", response_model=schemas.StatsOut)
def get_stats(db: Session = Depends(get_db)):
    total_seances = db.query(models.Seance).filter(models.Seance.statut == "terminee").count()
    total_modules = db.query(models.SessionApprentissage).count()

    rpe_avg = db.query(func.avg(models.Seance.rpe)).filter(models.Seance.rpe.isnot(None)).scalar()

    streak_rows = (
        db.query(models.Streak)
        .filter((models.Streak.sport_fait == 1) | (models.Streak.apprentissage_fait == 1))
        .order_by(models.Streak.date.desc())
        .all()
    )
    active_dates = {r.date for r in streak_rows}

    current_streak = 0
    cursor = date.today()
    while cursor in active_dates:
        current_streak += 1
        cursor -= timedelta(days=1)

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
