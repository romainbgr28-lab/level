import logging
import os
from datetime import date, timedelta
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func
from sqlalchemy.orm import Session

import mistral_client
import models
import regles_seance
import schemas
from calendrier import compute_phase
from database import Base, SessionLocal, engine, get_db
from seed import seed

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("level")

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


@app.delete("/api/seances/today", status_code=204)
def delete_today_seance(db: Session = Depends(get_db)):
    """Supprime la/les séance(s) du jour pour forcer une nouvelle génération.

    Endpoint temporaire, exposé via un bouton de reset côté écran Aujourd'hui,
    utile notamment pour effacer une séance restée en base d'avant le passage
    au flux 100% généré par /api/seance/generer.
    """
    db.query(models.Seance).filter(models.Seance.date == date.today()).delete()
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


def _construire_prompt_generation(profil: dict, recommandation: dict, etat_du_jour: dict) -> str:
    exclusions = recommandation.get("exclusions") or []
    exclusions_txt = ", ".join(exclusions) if exclusions else "aucune"
    raisons_txt = "; ".join(recommandation.get("raisons") or []) or "aucune"

    return f"""Tu es un coach sportif qui construit une séance de sport concrète pour un joueur de football amateur.

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

CONSIGNE
Construis une séance concrète respectant strictement l'intensité maximale et les exclusions
ci-dessus, cohérente avec le poste et le matériel disponible.
Réponds UNIQUEMENT avec un objet JSON valide, sans aucun texte avant ni après, au format exact
suivant :
{{
  "nom_seance": "string",
  "duree_min": nombre entier de minutes,
  "exercices": [
    {{"nom": "string", "series": nombre entier, "repetitions": "string", "charge_indicative": "string", "notes": "string"}}
  ],
  "explication": "texte en français expliquant le pourquoi de cette séance (phase calendaire, poste, état du jour)"
}}"""


def _construire_prompt_extraction(seance: models.Seance, compte_rendu: str) -> str:
    return f"""Tu extrais des données structurées à partir du compte-rendu libre d'un joueur après une séance de sport.

SÉANCE PRÉVUE
- Nom : {seance.nom}
- Exercices prévus : {seance.exercices}

COMPTE-RENDU DU JOUEUR (texte libre)
\"\"\"{compte_rendu}\"\"\"

CONSIGNE
Réponds UNIQUEMENT avec un objet JSON valide, sans aucun texte avant ni après, au format exact
suivant :
{{
  "exercices_realises": [{{"nom": "string", "series": nombre entier, "repetitions": "string", "charge": "string"}}],
  "rpe": nombre entier de 1 à 10 (déduit du compte-rendu, ta meilleure estimation si non explicite),
  "pourcentage_complete": nombre de 0 à 100 (pourcentage de la séance prévue réellement réalisé),
  "notes": "résumé court en français du compte-rendu",
  "zone_sensible_signalee": "nom de la zone/du groupe musculaire si le joueur signale une gêne ou douleur, sinon null"
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
def generer_seance(payload: schemas.EtatDuJour, db: Session = Depends(get_db)):
    profil = db.query(models.Profil).order_by(models.Profil.id.desc()).first()
    if not profil:
        raise HTTPException(status_code=400, detail="Aucun profil enregistré : termine l'onboarding avant de générer une séance.")

    profil_dict = schemas.ProfilOut.model_validate(profil).model_dump(mode="json")
    historique_ctx = _construire_contexte_historique(db)
    etat_du_jour = payload.model_dump()

    recommandation = regles_seance.generer_recommandation(profil_dict, historique_ctx, etat_du_jour)
    prompt = _construire_prompt_generation(profil_dict, recommandation, etat_du_jour)

    try:
        data = mistral_client.appeler_mistral_json(prompt)
    except mistral_client.MistralError as exc:
        logger.error("Échec de la génération de séance via Mistral : %s", exc)
        raise HTTPException(status_code=502, detail=f"Le générateur de séance a échoué : {exc}") from exc

    required_keys = {"nom_seance", "duree_min", "exercices", "explication"}
    if not required_keys.issubset(data) or not isinstance(data.get("exercices"), list):
        logger.error("Réponse Mistral incomplète ou invalide (génération séance) : %s", data)
        raise HTTPException(status_code=502, detail="La séance générée par l'IA est incomplète ou mal formée.")

    seance = models.Seance(
        date=date.today(),
        nom=data["nom_seance"],
        exercices=data["exercices"],
        statut="prévue",
        type_seance=recommandation["type_seance_suggere"],
        explication=data.get("explication"),
        duree_reelle=None,
    )
    db.add(seance)
    db.commit()
    db.refresh(seance)

    return schemas.SeanceGenereeOut(
        id=seance.id,
        nom_seance=data["nom_seance"],
        duree_min=int(data.get("duree_min") or 45),
        exercices=data["exercices"],
        explication=data.get("explication", ""),
        recommandation=recommandation,
    )


@app.post("/api/seance/terminer", response_model=schemas.TerminerSeanceOut)
def terminer_seance(payload: schemas.TerminerSeancePayload, db: Session = Depends(get_db)):
    seance = db.get(models.Seance, payload.seance_id)
    if not seance:
        raise HTTPException(status_code=404, detail="Séance introuvable")

    prompt = _construire_prompt_extraction(seance, payload.compte_rendu)

    try:
        data = mistral_client.appeler_mistral_json(prompt)
    except mistral_client.MistralError as exc:
        logger.error("Échec de l'extraction du compte-rendu via Mistral : %s", exc)
        raise HTTPException(status_code=502, detail=f"L'analyse du compte-rendu a échoué : {exc}") from exc

    required_keys = {"exercices_realises", "rpe", "pourcentage_complete"}
    if not required_keys.issubset(data):
        logger.error("Réponse Mistral incomplète ou invalide (extraction compte-rendu) : %s", data)
        raise HTTPException(status_code=502, detail="L'extraction du compte-rendu par l'IA est incomplète ou mal formée.")

    rpe = data.get("rpe")
    rpe = int(rpe) if isinstance(rpe, (int, float)) else None
    pourcentage_complete = data.get("pourcentage_complete")
    pourcentage_complete = float(pourcentage_complete) if isinstance(pourcentage_complete, (int, float)) else None

    seance.statut = "terminee"
    seance.rpe = rpe
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

    historique = models.HistoriqueSeance(
        date=seance.date,
        phase_calendaire=phase,
        type_seance=seance.type_seance or seance.nom,
        exercices_prevus=seance.exercices,
        exercices_realises=data.get("exercices_realises") or [],
        rpe=rpe,
        pourcentage_complete=pourcentage_complete,
        zone_sensible_signalee=data.get("zone_sensible_signalee") or None,
        xp_gagne=xp_gagne,
        notes=data.get("notes"),
        etat_declare_avant={},
    )
    db.add(historique)
    db.commit()
    db.refresh(historique)

    return schemas.TerminerSeanceOut(resume=data, xp_gagne=xp_gagne, historique_id=historique.id)


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
