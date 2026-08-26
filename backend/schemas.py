from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

import user_model_v2


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


# ---------- User Model V2 (voir user_model_v2.py) ----------


class ObjectifV2(BaseModel):
    """Un objectif hiérarchisé. `poids` est toujours recalculé côté backend à
    partir du rang (voir user_model_v2.poids_par_defaut) — jamais une entrée
    de confiance venant du client : le frontend ne doit pas être source de
    vérité sur les poids (Phase 2)."""

    theme: str
    rang: int
    poids: float

    @field_validator("theme")
    @classmethod
    def _theme_valide(cls, v: str) -> str:
        if v not in user_model_v2.THEMES_OBJECTIFS_V2:
            raise ValueError(f"theme invalide : {v!r} (attendu un de {user_model_v2.THEMES_OBJECTIFS_V2})")
        return v


class ContexteSportif(BaseModel):
    """Sport pratiqué, distinct de l'objectif sportif (voir user_model_v2.py :
    RÈGLE FONDAMENTALE, sport pratiqué != objectif)."""

    sport: Optional[str] = None  # None | "football" | libellé libre d'un autre sport
    frequence_hebdo: Optional[int] = None
    poste: Optional[str] = None  # pertinent seulement si sport == "football"


class ProfilBase(BaseModel):
    # --- Champs legacy (conservés pour compatibilité descendante, voir Phase 1) ---
    # Rendus optionnels ici : un client V2 n'a plus à les envoyer, ils sont dérivés
    # côté backend à partir des champs V2 (voir main.py::upsert_profil et
    # user_model_v2.py). Restent cependant NOT NULL en base — la dérivation garantit
    # toujours une valeur avant l'écriture.
    objectifs: list[str] = []
    poste: str = ""
    age: int
    taille_cm: float
    poids_kg: float
    niveau_physique: str
    niveaux_qualites_physiques: QualitesPhysiques
    calendrier_matchs: CalendrierMatchs
    objectif_esthetique: Optional[ObjectifEsthetique] = None
    contraintes_temps: str = ""
    materiel: str

    # --- Champs V2 ---
    # Optionnels en entrée : si absents, dérivés depuis les champs legacy ci-dessus
    # (migration automatique, voir user_model_v2.normaliser_objectifs /
    # normaliser_disponibilites). Toujours normalisés/recalculés côté backend avant
    # stockage : jamais pris tels quels depuis le client (voir upsert_profil).
    objectifs_v2: list[ObjectifV2] = []
    contexte_sportif: ContexteSportif = ContexteSportif()
    disponibilites: dict[str, Optional[int]] = {}

    @model_validator(mode="before")
    @classmethod
    def _tolerer_colonnes_non_migrees(cls, data: Any) -> Any:
        """Un profil créé avant l'introduction des colonnes V2 (voir migrate.py) a ces
        colonnes à NULL en base -> l'ORM les expose comme None. Sans ce garde-fou, la
        validation stricte des champs V2 échouerait à la simple lecture d'un ancien
        profil (violerait Phase 9 : pas de crash sur données non migrées)."""
        # `data` est soit un dict (payload entrant), soit un objet ORM (lecture depuis
        # la DB, model_config.from_attributes=True) : on ne mute que le cas dict ici,
        # le cas ORM est neutralisé plus bas par une lecture défensive équivalente.
        if isinstance(data, dict):
            for champ in ("objectifs_v2", "contexte_sportif", "disponibilites"):
                if data.get(champ) is None:
                    data[champ] = [] if champ == "objectifs_v2" else {}
            return data

        # Objet ORM (lecture DB, from_attributes=True) : on ne mute jamais l'instance
        # SQLAlchemy suivie par la session (éviterait un flush accidentel d'une valeur
        # vide écrasant le NULL réel) — on construit un dict détaché à la place.
        detache = {champ: getattr(data, champ, None) for champ in cls.model_fields}
        # Un profil lu depuis la DB sans contexte_sportif jamais renseigné est par
        # construction un ancien profil (l'app n'a longtemps été que football) : on
        # infère sport="football" à partir de `poste` pour la lecture uniquement, afin
        # de ne pas régresser le comportement existant (Phase 9). Un payload entrant
        # (POST /api/profil) n'est jamais concerné par cette inférence — voir la
        # branche dict ci-dessus, qui respecte toujours ce que le client envoie
        # explicitement (y compris contexte_sportif.sport=None).
        if detache.get("contexte_sportif") is None:
            detache["contexte_sportif"] = {"sport": None, "frequence_hebdo": None, "poste": None}
            poste_legacy = detache.get("poste")
            if poste_legacy in user_model_v2.POSTES_FOOTBALL:
                detache["contexte_sportif"] = {"sport": "football", "frequence_hebdo": None, "poste": poste_legacy}
        for champ in ("objectifs_v2", "disponibilites"):
            if detache.get(champ) is None:
                detache[champ] = [] if champ == "objectifs_v2" else {}
        return detache

    @model_validator(mode="after")
    def _normaliser_v2(self) -> "ProfilBase":
        # Objectifs V2 : si le client envoie déjà objectifs_v2, on le renormalise
        # quand même (recalcule les poids depuis les rangs, jamais depuis le client) ;
        # sinon on migre depuis l'ancien format `objectifs` (list[str]).
        source_objectifs = (
            [o.model_dump() for o in self.objectifs_v2] if self.objectifs_v2 else self.objectifs
        )
        objectifs_normalises = user_model_v2.normaliser_objectifs(source_objectifs)
        self.objectifs_v2 = [ObjectifV2(**o) for o in objectifs_normalises]

        # Contexte sportif : normalisation (poste ignoré si sport != football).
        self.contexte_sportif = ContexteSportif(
            **user_model_v2.normaliser_contexte_sportif(self.contexte_sportif.model_dump())
        )

        # Disponibilités : dict structuré si fourni, sinon fallback best-effort sur
        # l'ancien `contraintes_temps` texte libre (Phase 3/4).
        self.disponibilites = user_model_v2.normaliser_disponibilites(
            self.disponibilites, fallback_contraintes_temps=self.contraintes_temps or None
        )

        # Dérivation des champs legacy depuis les champs V2 quand le client V2 ne les
        # a pas fournis, pour ne jamais violer les contraintes NOT NULL existantes ni
        # perdre l'info pour le code qui lit encore l'ancien format.
        if not self.poste and self.contexte_sportif.poste:
            self.poste = self.contexte_sportif.poste
        if not self.objectifs and self.objectifs_v2:
            self.objectifs = [o.theme for o in self.objectifs_v2]

        return self


class ProfilCreate(ProfilBase):
    pass


class ProfilOut(ProfilBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    date_creation: Optional[datetime] = None
    niveau_observe: Optional[dict[str, Any]] = None


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
    # Champs normalisés pour le remplacement d'exercice (Étape 7C) — voir substitution.py.
    pattern_mouvement: Optional[str] = None
    groupe_musculaire_principal: Optional[str] = None
    materiel_requis_liste: Optional[list[str]] = None


class ExerciceBibliothequeCreate(ExerciceBibliothequeBase):
    pass


class ExerciceBibliothequeOut(ExerciceBibliothequeBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


# ---------- Remplacement d'exercice (Étape 7C) ----------


class AlternativeExerciceOut(BaseModel):
    """Un candidat de remplacement, avec de quoi l'afficher et expliquer le score côté UI."""

    exercice: ExerciceBibliothequeOut
    score: int
    memes_criteres: list[str]  # ex: ["pattern_mouvement", "groupe_musculaire_principal"]


class AlternativesExerciceOut(BaseModel):
    exercice_actuel_id: int
    alternatives: list[AlternativeExerciceOut]


class RemplacerExercicePayload(BaseModel):
    exercice_id_actuel: int
    exercice_id_nouveau: int


class RemplacerExerciceOut(BaseModel):
    seance: SeanceOut
    series_deja_realisees: int  # nb de séries cochées sur l'ancien exercice, pour l'UI de confirmation
    message_confirmation: Optional[str] = None


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
