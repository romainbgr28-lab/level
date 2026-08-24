from sqlalchemy import Column, Integer, String, Float, JSON, Date, DateTime, ForeignKey
from sqlalchemy.sql import func

from database import Base


class Profil(Base):
    __tablename__ = "profil"

    id = Column(Integer, primary_key=True, index=True)
    objectifs = Column(JSON, nullable=False, default=list)
    poste = Column(String, nullable=False)  # Gardien | Défenseur | Milieu | Attaquant
    niveau_physique = Column(String, nullable=False)  # résumé auto (Débutant/Intermédiaire/Avancé)
    niveaux_qualites_physiques = Column(JSON, nullable=False, default=dict)  # {force, explosivite, vitesse, endurance}: 1-5
    niveau_intellectuel = Column(String, nullable=False)
    calendrier_matchs = Column(JSON, nullable=False, default=dict)  # {jour_habituel, exceptions: [{date, label}]}
    objectif_esthetique = Column(JSON, nullable=True)  # {tags: [...], texte_libre: str} | null
    contraintes_temps = Column(String, nullable=False)
    materiel = Column(String, nullable=False)
    date_creation = Column(DateTime, server_default=func.now())


class Seance(Base):
    __tablename__ = "seances"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False)
    nom = Column(String, nullable=False)
    exercices = Column(JSON, nullable=False, default=list)
    statut = Column(String, nullable=False, default="planifiee")  # planifiee | terminee
    rpe = Column(Integer, nullable=True)
    duree_reelle = Column(Integer, nullable=True)  # minutes


class ExerciceHistorique(Base):
    __tablename__ = "exercices_historique"

    id = Column(Integer, primary_key=True, index=True)
    seance_id = Column(Integer, ForeignKey("seances.id"), nullable=False)
    nom_exercice = Column(String, nullable=False)
    series = Column(Integer, nullable=False)
    repetitions = Column(Integer, nullable=False)
    charge_kg = Column(Float, nullable=False)
    date = Column(Date, nullable=False)


class ModuleIntellectuel(Base):
    __tablename__ = "modules_intellectuels"

    id = Column(Integer, primary_key=True, index=True)
    categorie = Column(String, nullable=False)
    niveau = Column(String, nullable=False)
    titre = Column(String, nullable=False)
    contenu = Column(String, nullable=False)
    questions = Column(JSON, nullable=False, default=list)


class SessionApprentissage(Base):
    __tablename__ = "sessions_apprentissage"

    id = Column(Integer, primary_key=True, index=True)
    module_id = Column(Integer, ForeignKey("modules_intellectuels.id"), nullable=False)
    date = Column(Date, nullable=False)
    reponses = Column(JSON, nullable=False, default=dict)
    score = Column(Float, nullable=True)


class Streak(Base):
    __tablename__ = "streaks"

    date = Column(Date, primary_key=True)
    sport_fait = Column(Integer, nullable=False, default=0)  # 0/1 bool
    apprentissage_fait = Column(Integer, nullable=False, default=0)  # 0/1 bool


class HistoriqueSeance(Base):
    """Journal détaillé d'une séance : ce qui était prévu vs réalisé, contexte déclaré
    avant la séance, et la phase du calendrier de matchs au moment de la séance."""

    __tablename__ = "historique_seances"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False)
    phase_calendaire = Column(String, nullable=False)  # calculée serveur (cf. calendrier.py)
    type_seance = Column(String, nullable=False)
    exercices_prevus = Column(JSON, nullable=False, default=list)
    exercices_realises = Column(JSON, nullable=False, default=list)
    rpe = Column(Integer, nullable=True)
    notes = Column(String, nullable=True)
    etat_declare_avant = Column(JSON, nullable=False, default=dict)  # {sommeil, motivation, temps_dispo, envie_texte}
