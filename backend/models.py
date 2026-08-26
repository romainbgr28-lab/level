from sqlalchemy import Column, Integer, String, Float, JSON, Date, DateTime, ForeignKey
from sqlalchemy.sql import func

from database import Base


class Profil(Base):
    __tablename__ = "profil"

    id = Column(Integer, primary_key=True, index=True)
    objectifs = Column(JSON, nullable=False, default=list)
    poste = Column(String, nullable=False)  # Gardien | Défenseur | Milieu | Attaquant
    age = Column(Integer, nullable=False)
    taille_cm = Column(Float, nullable=False)
    poids_kg = Column(Float, nullable=False)
    niveau_physique = Column(String, nullable=False)  # résumé auto (Débutant/Intermédiaire/Avancé)
    niveaux_qualites_physiques = Column(JSON, nullable=False, default=dict)  # {force, explosivite, vitesse, endurance}: 1-5
    calendrier_matchs = Column(JSON, nullable=False, default=dict)  # {jour_habituel, exceptions, entrainements_club}
    objectif_esthetique = Column(JSON, nullable=True)  # {tags: [...], texte_libre: str} | null
    contraintes_temps = Column(String, nullable=False)
    materiel = Column(String, nullable=False)
    date_creation = Column(DateTime, server_default=func.now())

    # --- User Model V2 (voir user_model_v2.py) --------------------------------------------
    # Colonnes additives (nullable, ajoutées par migrate.py) : les colonnes ci-dessus
    # (objectifs, poste, contraintes_temps, calendrier_matchs...) restent la représentation
    # "legacy" toujours écrite en parallèle par compatibilité descendante (aucune lecture ne
    # doit crasher sur un profil non migré). Les colonnes ci-dessous sont la nouvelle source
    # de vérité structurée, normalisée par user_model_v2.py à l'écriture (voir main.py::upsert_profil).
    objectifs_v2 = Column(JSON, nullable=True)  # list[{theme, rang, poids}], max 3
    contexte_sportif = Column(JSON, nullable=True)  # {sport, frequence_hebdo, poste}
    disponibilites = Column(JSON, nullable=True)  # {lundi: minutes|None, ..., dimanche: minutes|None}
    # Niveau observé recalculé à partir des séances réalisées, par qualité physique :
    # {force: {"valeur": float|None, "confiance": float, "n_seances": int}, ...}. None tant
    # qu'aucune séance comparable n'a été terminée pour cette qualité (voir calculer_niveau_observe).
    niveau_observe = Column(JSON, nullable=True)


class Seance(Base):
    __tablename__ = "seances"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False)
    nom = Column(String, nullable=False)
    # Chaque item : {"exercice_id": int, "series": int, "repetitions": str,
    # "charge_indicative": str|None, "notes": str|None} — exercice_id référence
    # exercices_bibliotheque.id (plus de nom texte libre inventé par l'IA).
    # Optionnel : "historique_exercice_ids": list[int], présent uniquement si l'exercice de ce
    # slot a déjà été remplacé au moins une fois (Étape 7C, voir main.py::remplacer_exercice) —
    # trace la chaîne A -> B -> C sans jamais réécrire les SerieLoggee déjà persistées.
    exercices = Column(JSON, nullable=False, default=list)
    statut = Column(String, nullable=False, default="planifiee")  # planifiee | prévue | terminee
    type_seance = Column(String, nullable=True)  # force | explosivité_vitesse | esthétique | décharge (moteur de règles)
    explication = Column(String, nullable=True)  # explication IA associée à la séance générée
    rpe = Column(Integer, nullable=True)
    duree_prevue = Column(Integer, nullable=True)  # minutes, estimée par le calibrage temps_dispo à la génération
    duree_reelle = Column(Integer, nullable=True)  # minutes, déclarée par le joueur en fin de séance
    note = Column(String, nullable=True)  # ressenti général en fin de séance, texte libre optionnel
    # État déclaré par le joueur AVANT la génération de cette séance (mêmes champs que
    # schemas.EtatDeclareAvant) : capturé ici à la génération pour que terminer_seance() puisse
    # le reporter fidèlement dans HistoriqueSeance, sans le redemander ni le reconstruire.
    etat_declare_avant = Column(JSON, nullable=True)
    # Décision d'adaptation réellement appliquée à cette séance (recommandation du moteur de
    # règles + corrections déterministes post-génération, cf. main.py::generer_seance et
    # _corriger_charges_hors_tolerance). Copiée telle quelle dans HistoriqueSeance.decision_adaptation
    # par terminer_seance().
    decision_adaptation = Column(JSON, nullable=True)


class ExerciceBibliotheque(Base):
    """Catalogue d'exercices dans lequel Mistral doit puiser pour générer une séance
    (voir main.py::_construire_prompt_generation) plutôt que d'en inventer.

    Structure prête, volontairement non peuplée pour l'instant : le contenu réel
    (instructions détaillées, images) sera fourni séparément.
    """

    __tablename__ = "exercices_bibliotheque"

    id = Column(Integer, primary_key=True, index=True)
    nom = Column(String, nullable=False)
    groupe_musculaire = Column(String, nullable=False)
    instructions = Column(JSON, nullable=False, default=list)  # liste de points (str)
    image_url = Column(String, nullable=True)  # placeholder pour l'instant
    type = Column(String, nullable=False)  # force | explosivite | technique | récupération
    materiel_requis = Column(String, nullable=True)  # ex: "aucun", "haltères", "banc ou support surélevé"
    sport_specifique = Column(String, nullable=True)  # "foot" | "généraliste"
    points_securite = Column(String, nullable=True)
    # --- Étape 7C (remplacement d'exercice) : champs normalisés, en complément du texte
    # libre ci-dessus, pour permettre un matching déterministe entre exercices (voir
    # substitution.py). Nullable et rétro-annotés par seed.py plutôt que migrés en dur,
    # pour rester idempotent sur une base déjà peuplée.
    pattern_mouvement = Column(String, nullable=True)  # ex: squat | hinge | fente | poussee_horizontale | ...
    groupe_musculaire_principal = Column(String, nullable=True)  # valeur unique normalisée (vs groupe_musculaire, texte libre)
    materiel_requis_liste = Column(JSON, nullable=True)  # liste de tags matériel normalisés, ex: ["haltères"], []
    # Nature de la charge adaptée à cet exercice, indépendante du niveau de force déclaré par
    # l'utilisateur : poids_du_corps | charge_legere | charge_moderee | charge_lourde_progressive.
    # Sert de garde-fou pour Mistral (voir main.py::_construire_prompt_generation) afin d'éviter
    # une charge incohérente (ex: squat jump chargé à 40kg).
    charge_recommandee = Column(String, nullable=False, default="charge_moderee")


class SerieLoggee(Base):
    """Une série effectivement loguée en temps réel pendant une séance (façon Hevy)."""

    __tablename__ = "series_loggees"

    id = Column(Integer, primary_key=True, index=True)
    seance_id = Column(Integer, ForeignKey("seances.id"), nullable=False)
    exercice_id = Column(Integer, ForeignKey("exercices_bibliotheque.id"), nullable=False)
    numero_serie = Column(Integer, nullable=False)
    poids_kg = Column(Float, nullable=True)
    repetitions = Column(Integer, nullable=True)
    # Prévu, calculé et persisté côté serveur à la création (voir main.py::_prevu_pour_exercice),
    # à partir de Seance.exercices — jamais fourni par le client. Nullable : colonne ajoutée après
    # coup (voir migrate.py), les séries loguées avant restent valides sans ces valeurs.
    reps_prevues = Column(Integer, nullable=True)
    charge_prevue_kg = Column(Float, nullable=True)
    coche = Column(Integer, nullable=False, default=0)  # 0/1 bool
    # Validation rapide par bouton : "facile" | "comme_prevu" | "dur" -> rpe_approx
    # calculé côté serveur (voir main.py::DIFFICULTE_RPE_APPROX). L'utilisateur peut
    # rester sur ce bouton ou affiner poids_kg/repetitions/rpe_approx via "Modifier".
    difficulte = Column(String, nullable=True)
    rpe_approx = Column(Integer, nullable=True)
    horodatage = Column(DateTime, server_default=func.now())


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


class Programme(Base):
    """Programme structuré sur 8 semaines (par défaut), généré par Mistral à partir
    du profil complet. Indépendant de la génération de séance quotidienne
    (/api/seance/generer) : sert de trame globale, pas de séance concrète."""

    __tablename__ = "programme"

    id = Column(Integer, primary_key=True, index=True)
    utilisateur_id = Column(Integer, nullable=False)
    date_debut = Column(Date, nullable=False)
    duree_semaines = Column(Integer, nullable=False, default=8)
    # Liste de 3 blocs {nom, semaines: [debut, fin], description}
    phases = Column(JSON, nullable=False, default=list)
    # {jour: "Lundi"|...: type_seance: "force"|"explosivité_vitesse"|"esthétique"|"repos"}
    gabarit_hebdomadaire = Column(JSON, nullable=False, default=dict)
    # {force: [pct_semaine_1, ..., pct_semaine_8], explosivite: [...], esthetique: [...]}
    trajectoire_progression = Column(JSON, nullable=False, default=dict)
    statut = Column(String, nullable=False, default="actif")  # actif | terminé
    date_creation = Column(DateTime, server_default=func.now())


class NiveauHistorique(Base):
    """Journal des changements de niveau déclaré/estimé par qualité physique."""

    __tablename__ = "niveau_historique"

    id = Column(Integer, primary_key=True, index=True)
    utilisateur_id = Column(Integer, nullable=False)
    qualite = Column(String, nullable=False)  # force | explosivite | vitesse | endurance
    ancien_niveau = Column(Integer, nullable=False)
    nouveau_niveau = Column(Integer, nullable=False)
    date = Column(Date, nullable=False)
    critere_declencheur = Column(String, nullable=False)


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
    pourcentage_complete = Column(Float, nullable=True)
    zone_sensible_signalee = Column(String, nullable=True)
    xp_gagne = Column(Integer, nullable=True)
    notes = Column(String, nullable=True)
    etat_declare_avant = Column(JSON, nullable=False, default=dict)  # {sommeil, motivation, temps_dispo, envie_texte, entrainement_club_semaine}
    # Décision d'adaptation réellement appliquée à la Seance liée (recommandation du moteur de
    # règles + corrections déterministes post-génération, cf. main.py::generer_seance), copiée
    # telle quelle depuis Seance.decision_adaptation par terminer_seance(). Peut rester null
    # pour les séances terminées avant l'introduction de cette colonne (cf. migrate.py).
    decision_adaptation = Column(JSON, nullable=True)
