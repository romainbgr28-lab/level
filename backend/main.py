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
    serie = models.SerieLoggee(**data)
    db.add(serie)
    db.commit()
    db.refresh(serie)
    return serie


@app.patch("/api/series_loggees/{serie_id}", response_model=schemas.SerieLoggeeOut)
def update_serie_loggee(serie_id: int, payload: schemas.SerieLoggeeUpdate, db: Session = Depends(get_db)):
    serie = db.get(models.SerieLoggee, serie_id)
    if not serie:
        raise HTTPException(status_code=404, detail="Série introuvable")
    for key, value in payload.model_dump(exclude_unset=True).items():
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


def _construire_prompt_generation(
    profil: dict, recommandation: dict, etat_du_jour: dict, bibliotheque: list[models.ExerciceBibliotheque]
) -> str:
    exclusions = recommandation.get("exclusions") or []
    exclusions_txt = ", ".join(exclusions) if exclusions else "aucune"
    raisons_txt = "; ".join(recommandation.get("raisons") or []) or "aucune"

    bibliotheque_txt = "\n".join(
        f"- id {ex.id} : {ex.nom} (groupe musculaire : {ex.groupe_musculaire}, type : {ex.type})"
        for ex in bibliotheque
    )

    return f"""Tu es un coach sportif qui construit une séance de sport concrète pour un joueur de football amateur.

EXERCICES DISPONIBLES (bibliothèque — tu dois obligatoirement choisir les exercices de la séance
UNIQUEMENT parmi cette liste, en référençant leur id ; interdiction stricte d'inventer un exercice
qui n'y figure pas)
{bibliotheque_txt}

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
ci-dessus, cohérente avec le poste et le matériel disponible, en choisissant exclusivement des
exercices dont l'id figure dans la liste EXERCICES DISPONIBLES ci-dessus.
Réponds UNIQUEMENT avec un objet JSON valide, sans aucun texte avant ni après, au format exact
suivant :
{{
  "nom_seance": "string",
  "duree_min": nombre entier de minutes,
  "exercices": [
    {{"exercice_id": nombre entier (id pris dans la liste EXERCICES DISPONIBLES), "series": nombre entier, "repetitions": "string", "charge_indicative": "string", "notes": "string"}}
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
def generer_seance(payload: schemas.EtatDuJour, db: Session = Depends(get_db)):
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

    recommandation = regles_seance.generer_recommandation(profil_dict, historique_ctx, etat_du_jour)
    prompt = _construire_prompt_generation(profil_dict, recommandation, etat_du_jour, bibliotheque)

    try:
        data = mistral_client.appeler_mistral_json(prompt)
    except mistral_client.MistralError as exc:
        logger.error("Échec de la génération de séance via Mistral : %s", exc)
        raise HTTPException(status_code=502, detail=f"Le générateur de séance a échoué : {exc}") from exc

    required_keys = {"nom_seance", "duree_min", "exercices", "explication"}
    if not required_keys.issubset(data) or not isinstance(data.get("exercices"), list):
        logger.error("Réponse Mistral incomplète ou invalide (génération séance) : %s", data)
        raise HTTPException(status_code=502, detail="La séance générée par l'IA est incomplète ou mal formée.")

    ids_valides = {ex.id for ex in bibliotheque}
    if not all(isinstance(item, dict) and item.get("exercice_id") in ids_valides for item in data["exercices"]):
        logger.error("Réponse Mistral avec exercice_id hors bibliothèque : %s", data)
        raise HTTPException(status_code=502, detail="La séance générée par l'IA référence un exercice hors bibliothèque.")

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
    """Calcule la fin de séance à partir des vraies données de series_loggees
    (plus d'IA pour interpréter un compte-rendu texte libre). Le RPE est déclaré
    directement par le joueur ; `note` reste un texte libre optionnel pour le
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

    rpe = payload.rpe
    seance.statut = "terminee"
    seance.rpe = rpe
    seance.note = payload.note
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
