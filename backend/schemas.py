from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class QualitesPhysiques(BaseModel):
    force: int
    explosivite: int
    vitesse: int
    endurance: int


class CalendrierException(BaseModel):
    date: date
    label: Optional[str] = None


class EntrainementsClub(BaseModel):
    actif: bool
    seances_par_semaine: Optional[int] = None


class CalendrierMatchs(BaseModel):
    jour_habituel: Optional[str] = None
    exceptions: list[CalendrierException] = []
    entrainements_club: Optional[EntrainementsClub] = None


class ObjectifEsthetique(BaseModel):
    tags: list[str] = []
    texte_libre: Optional[str] = None


class ProfilBase(BaseModel):
    objectifs: list[str]
    poste: str
    niveau_physique: str
    niveaux_qualites_physiques: QualitesPhysiques
    calendrier_matchs: CalendrierMatchs
    objectif_esthetique: Optional[ObjectifEsthetique] = None
    contraintes_temps: str
    materiel: str


class ProfilCreate(ProfilBase):
    pass


class ProfilOut(ProfilBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    date_creation: Optional[datetime] = None


class SeanceExerciceItem(BaseModel):
    """Item de la liste `exercices` d'une séance : référence un exercice de la
    bibliothèque par id (Mistral doit choisir parmi l'existant, pas inventer)."""

    exercice_id: int
    series: int
    repetitions: str
    charge_indicative: Optional[str] = None
    notes: Optional[str] = None


class SeanceBase(BaseModel):
    date: date
    nom: str
    exercices: list[dict[str, Any]]
    statut: str = "planifiee"
    type_seance: Optional[str] = None
    explication: Optional[str] = None
    rpe: Optional[int] = None
    duree_reelle: Optional[int] = None
    note: Optional[str] = None


class SeanceCreate(SeanceBase):
    pass


class SeanceUpdate(BaseModel):
    statut: Optional[str] = None
    rpe: Optional[int] = None
    duree_reelle: Optional[int] = None
    exercices: Optional[list[dict[str, Any]]] = None
    note: Optional[str] = None


class SeanceOut(SeanceBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


# ---------- Bibliothèque d'exercices ----------


class ExerciceBibliothequeBase(BaseModel):
    nom: str
    groupe_musculaire: str
    instructions: list[str] = []
    image_url: Optional[str] = None
    type: str  # force | explosivite | technique | récupération
    materiel_requis: Optional[str] = None
    sport_specifique: Optional[str] = None  # "foot" | "généraliste"
    points_securite: Optional[str] = None


class ExerciceBibliothequeCreate(ExerciceBibliothequeBase):
    pass


class ExerciceBibliothequeOut(ExerciceBibliothequeBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


# ---------- Séries loguées en temps réel (façon Hevy) ----------


class SerieLoggeeBase(BaseModel):
    seance_id: int
    exercice_id: int
    numero_serie: int
    poids_kg: Optional[float] = None
    repetitions: Optional[int] = None
    coche: bool = False


class SerieLoggeeCreate(SerieLoggeeBase):
    pass


class SerieLoggeeUpdate(BaseModel):
    poids_kg: Optional[float] = None
    repetitions: Optional[int] = None
    coche: Optional[bool] = None


class SerieLoggeeOut(SerieLoggeeBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    horodatage: Optional[datetime] = None


class DernierePerformanceOut(BaseModel):
    """« Précédent » façon Hevy : les séries de la dernière fois où cet exercice a été loggé."""

    date: Optional[date] = None
    series: list[SerieLoggeeOut] = []


class ExerciceHistoriqueBase(BaseModel):
    seance_id: int
    nom_exercice: str
    series: int
    repetitions: int
    charge_kg: float
    date: date


class ExerciceHistoriqueCreate(ExerciceHistoriqueBase):
    pass


class ExerciceHistoriqueOut(ExerciceHistoriqueBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class ModuleBase(BaseModel):
    categorie: str
    niveau: str
    titre: str
    contenu: str
    questions: list[dict[str, Any]]


class ModuleCreate(ModuleBase):
    pass


class ModuleOut(ModuleBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class SessionApprentissageBase(BaseModel):
    module_id: int
    date: date
    reponses: dict[str, Any]
    score: Optional[float] = None


class SessionApprentissageCreate(SessionApprentissageBase):
    pass


class SessionApprentissageOut(SessionApprentissageBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class StreakBase(BaseModel):
    date: date
    sport_fait: bool
    apprentissage_fait: bool


class StreakOut(StreakBase):
    model_config = ConfigDict(from_attributes=True)


class EtatDeclareAvant(BaseModel):
    sommeil: Optional[str] = None
    motivation: Optional[str] = None
    temps_dispo: Optional[str] = None
    envie_texte: Optional[str] = None
    entrainement_club_semaine: Optional[str] = None  # "non" | "1_fois" | "2_fois_ou_plus"


class HistoriqueSeanceBase(BaseModel):
    date: date
    type_seance: str
    exercices_prevus: list[dict[str, Any]] = []
    exercices_realises: list[dict[str, Any]] = []
    rpe: Optional[int] = None
    pourcentage_complete: Optional[float] = None
    zone_sensible_signalee: Optional[str] = None
    notes: Optional[str] = None
    etat_declare_avant: EtatDeclareAvant = EtatDeclareAvant()


class HistoriqueSeanceCreate(HistoriqueSeanceBase):
    pass  # phase_calendaire n'est pas fourni par le client : calculé côté serveur


class HistoriqueSeanceOut(HistoriqueSeanceBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    phase_calendaire: str
    xp_gagne: Optional[int] = None


class StatsOut(BaseModel):
    streak: int
    record_streak: int
    xp_total: int
    total_seances: int
    total_modules: int
    rpe_average: float


# ---------- Génération de séance assistée (moteur de règles + Mistral) ----------


class EtatDuJour(BaseModel):
    sommeil: Optional[str] = None
    motivation: Optional[str] = None
    temps_dispo: Optional[str] = None
    envie_texte: Optional[str] = None
    entrainement_club_semaine: Optional[str] = None  # "non" | "1_fois" | "2_fois_ou_plus"
    type_seance_force: Optional[str] = None  # override manuel : "force" | "explosivité_vitesse" | "esthétique" | "décharge"


class SeanceGenereeOut(BaseModel):
    id: int
    nom_seance: str
    duree_min: int
    exercices: list[dict[str, Any]]
    explication: str
    recommandation: dict[str, Any]  # transparence : la reco calculée qui a cadré Mistral


class TerminerSeancePayload(BaseModel):
    seance_id: int
    rpe: Optional[int] = None  # ressenti d'intensité (1-10), déclaré directement par le joueur
    note: Optional[str] = None  # ressenti général en texte libre, optionnel


class TerminerSeanceOut(BaseModel):
    resume: dict[str, Any]  # calculé à partir des series_loggees réelles (plus d'interprétation IA)
    xp_gagne: int
    historique_id: int
