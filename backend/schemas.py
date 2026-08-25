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
    age: int
    taille_cm: float
    poids_kg: float
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
    # Pré-remplissage calculé côté serveur (garde-fou temps + moteur de règles) : le
    # joueur n'a rien à saisir pour démarrer une série.
    rpe_cible: Optional[int] = None
    temps_repos_recommande_s: Optional[int] = None


class SeanceBase(BaseModel):
    date: date
    nom: str
    exercices: list[dict[str, Any]]
    statut: str = "planifiee"
    type_seance: Optional[str] = None
    explication: Optional[str] = None
    rpe: Optional[int] = None
    duree_prevue: Optional[int] = None
    duree_reelle: Optional[int] = None
    note: Optional[str] = None


class SeanceCreate(SeanceBase):
    pass


class SeanceUpdate(BaseModel):
    statut: Optional[str] = None
    rpe: Optional[int] = None
    duree_prevue: Optional[int] = None
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
    # poids_du_corps | charge_legere | charge_moderee | charge_lourde_progressive
    charge_recommandee: str = "charge_moderee"


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
    # Validation rapide par bouton (facile / comme_prevu / dur) : rpe_approx est
    # calculé côté serveur depuis difficulte si non fourni explicitement.
    difficulte: Optional[str] = None
    rpe_approx: Optional[int] = None


class SerieLoggeeCreate(SerieLoggeeBase):
    pass


class SerieLoggeeUpdate(BaseModel):
    poids_kg: Optional[float] = None
    repetitions: Optional[int] = None
    coche: Optional[bool] = None
    difficulte: Optional[str] = None
    rpe_approx: Optional[int] = None


class SerieLoggeeOut(SerieLoggeeBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    # Prévu, calculé et persisté côté serveur à la création (voir main.py::_prevu_pour_exercice) —
    # jamais fourni par le client. None sur les séries loguées avant l'introduction de ce champ.
    reps_prevues: Optional[int] = None
    charge_prevue_kg: Optional[float] = None
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


class HistoriqueSeanceOut(HistoriqueSeanceBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    phase_calendaire: str
    xp_gagne: Optional[int] = None
    decision_adaptation: Optional[dict[str, Any]] = None


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
    # Si le programme actif prévoit "repos" aujourd'hui, /api/seance/generer refuse par défaut
    # (409) : ce flag, positionné par le bouton "Je veux quand même faire une séance légère" côté
    # écran Aujourd'hui, force malgré tout une génération (type de séance ramené à "décharge").
    forcer_seance_legere: Optional[bool] = False


class SeanceGenereeOut(BaseModel):
    id: int
    nom_seance: str
    duree_min: int
    exercices: list[dict[str, Any]]
    explication: str
    recommandation: dict[str, Any]  # transparence : la reco calculée qui a cadré Mistral


class TerminerSeancePayload(BaseModel):
    seance_id: int
    # Override manuel optionnel : si absent, le RPE est déduit automatiquement de la
    # moyenne des rpe_approx (facile/comme prévu/dur) des séries validées.
    rpe: Optional[int] = None
    note: Optional[str] = None  # ressenti général en texte libre, optionnel
    duree_reelle_min: Optional[int] = None  # durée réellement écoulée, déclarée par le joueur
    # Zone sensible ressentie pendant la séance, valeur contrôlée parmi ZONES_SENSIBLES_VALIDES
    # (voir main.py) — réutilise exactement les libellés attendus par
    # regles_seance.GROUPES_PAR_TYPE_SEANCE pour garantir le matching côté garde-fous.
    zone_sensible: Optional[str] = None


class TerminerSeanceOut(BaseModel):
    resume: dict[str, Any]  # calculé à partir des series_loggees réelles (plus d'interprétation IA)
    xp_gagne: int
    historique_id: int


# ---------- Programme structuré (8 semaines) ----------


class ProgrammeGenererPayload(BaseModel):
    utilisateur_id: Optional[int] = None


class ProgrammeBase(BaseModel):
    utilisateur_id: int
    date_debut: date
    duree_semaines: int = 8
    phases: list[dict[str, Any]] = []
    gabarit_hebdomadaire: dict[str, Any] = {}
    trajectoire_progression: dict[str, Any] = {}
    statut: str = "actif"


class ProgrammeOut(ProgrammeBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    date_creation: Optional[datetime] = None


class NiveauHistoriqueBase(BaseModel):
    utilisateur_id: int
    qualite: str
    ancien_niveau: int
    nouveau_niveau: int
    date: date
    critere_declencheur: str


class NiveauHistoriqueOut(NiveauHistoriqueBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
