"""Rétro-annotation déterministe des exercices de la bibliothèque pour le
remplacement d'exercice (Étape 7C).

Table statique écrite à la main (pas d'IA à l'exécution), indexée par `nom`
exact tel que stocké dans ExerciceBibliotheque.nom — c'est la clé déjà
utilisée par seed.py pour dédupliquer les exercices, donc stable et unique.

Champs :
  - pattern_mouvement : famille de mouvement biomécanique (squat, hinge,
    poussee_horizontale, ...). Le seul critère de score le plus déterminant
    pour juger deux exercices interchangeables.
  - groupe_musculaire_principal : valeur normalisée unique (contrairement à
    ExerciceBibliotheque.groupe_musculaire, qui reste du texte libre affiché
    tel quel côté UI).
  - materiel_requis_liste : tags matériel normalisés, liste vide = aucun
    matériel requis.

Utilisée uniquement par seed.py pour rétro-annoter les lignes existantes
(colonnes nullable, backfill idempotent à chaque démarrage).
"""

ANNOTATIONS: dict[str, dict] = {
    # --- Base musculation (musculation_execution_exercices_base) ---
    "Squat (back squat / squat libre)": {
        "pattern_mouvement": "squat",
        "groupe_musculaire_principal": "jambes",
        "materiel_requis_liste": ["barre", "halteres"],
    },
    "Développé couché (bench press)": {
        "pattern_mouvement": "poussee_horizontale",
        "groupe_musculaire_principal": "pectoraux",
        "materiel_requis_liste": ["barre", "halteres"],
    },
    "Rowing buste penché (barbell row)": {
        "pattern_mouvement": "tirage_horizontal",
        "groupe_musculaire_principal": "dos",
        "materiel_requis_liste": ["barre", "halteres"],
    },
    "Soulevé de terre (deadlift)": {
        "pattern_mouvement": "hinge",
        "groupe_musculaire_principal": "chaine_posterieure",
        "materiel_requis_liste": ["barre", "halteres"],
    },
    # --- Extension (bibliotheque_exercices_extension) ---
    "Échauffement dynamique général": {
        "pattern_mouvement": "echauffement_general",
        "groupe_musculaire_principal": "corps_entier",
        "materiel_requis_liste": [],
    },
    "Échauffement articulaire ciblé (avant charge)": {
        "pattern_mouvement": "echauffement_general",
        "groupe_musculaire_principal": "corps_entier",
        "materiel_requis_liste": [],
    },
    "Sprint linéaire court (10-20m)": {
        "pattern_mouvement": "sprint",
        "groupe_musculaire_principal": "jambes",
        "materiel_requis_liste": [],
    },
    "Sprint lancé (accélération progressive puis vitesse max)": {
        "pattern_mouvement": "sprint",
        "groupe_musculaire_principal": "jambes",
        "materiel_requis_liste": [],
    },
    "Montées de genoux rapides sur place": {
        "pattern_mouvement": "deplacement_agilite",
        "groupe_musculaire_principal": "jambes",
        "materiel_requis_liste": [],
    },
    "Squat jump": {
        "pattern_mouvement": "saut_vertical",
        "groupe_musculaire_principal": "jambes",
        "materiel_requis_liste": [],
    },
    "Bondissement latéral (bounding)": {
        "pattern_mouvement": "saut_horizontal",
        "groupe_musculaire_principal": "jambes",
        "materiel_requis_liste": [],
    },
    "Saut avec réception contrôlée (jump and stick)": {
        "pattern_mouvement": "saut_vertical",
        "groupe_musculaire_principal": "jambes",
        "materiel_requis_liste": [],
    },
    "Sauts par-dessus obstacles bas (mini-haies ou lignes au sol)": {
        "pattern_mouvement": "saut_horizontal",
        "groupe_musculaire_principal": "jambes",
        "materiel_requis_liste": ["mini_haies"],
    },
    "Fentes sautées (jump lunges)": {
        "pattern_mouvement": "fente",
        "groupe_musculaire_principal": "jambes",
        "materiel_requis_liste": [],
    },
    "Medicine ball slam (lancer explosif au sol)": {
        "pattern_mouvement": "lancer_explosif",
        "groupe_musculaire_principal": "corps_entier",
        "materiel_requis_liste": ["medicine_ball"],
    },
    "Slalom entre plots (changement de direction)": {
        "pattern_mouvement": "deplacement_agilite",
        "groupe_musculaire_principal": "jambes",
        "materiel_requis_liste": ["plots"],
    },
    "Parcours en T (agilité multi-directionnelle)": {
        "pattern_mouvement": "deplacement_agilite",
        "groupe_musculaire_principal": "jambes",
        "materiel_requis_liste": ["plots"],
    },
    "Pas chassés / échelle de rythme (coordination)": {
        "pattern_mouvement": "deplacement_agilite",
        "groupe_musculaire_principal": "jambes",
        "materiel_requis_liste": ["echelle_rythme"],
    },
    "Exercice de réactivité sur signal": {
        "pattern_mouvement": "deplacement_agilite",
        "groupe_musculaire_principal": "jambes",
        "materiel_requis_liste": [],
    },
    "Fractionné 30-30 (endurance intermittente)": {
        "pattern_mouvement": "endurance_intermittente",
        "groupe_musculaire_principal": "jambes",
        "materiel_requis_liste": [],
    },
    "Fractionné 15-15 (haute intensité)": {
        "pattern_mouvement": "endurance_intermittente",
        "groupe_musculaire_principal": "jambes",
        "materiel_requis_liste": [],
    },
    "Circuit intermittent avec ballon": {
        "pattern_mouvement": "endurance_intermittente",
        "groupe_musculaire_principal": "jambes",
        "materiel_requis_liste": ["ballon", "plots"],
    },
    "Sprint en côte / montée": {
        "pattern_mouvement": "sprint",
        "groupe_musculaire_principal": "jambes",
        "materiel_requis_liste": [],
    },
    "Planche ventrale (gainage)": {
        "pattern_mouvement": "gainage",
        "groupe_musculaire_principal": "abdominaux",
        "materiel_requis_liste": [],
    },
    "Planche latérale (gainage)": {
        "pattern_mouvement": "gainage",
        "groupe_musculaire_principal": "obliques",
        "materiel_requis_liste": [],
    },
    "Nordic hamstring curl": {
        "pattern_mouvement": "hinge",
        "groupe_musculaire_principal": "ischio_jambiers",
        "materiel_requis_liste": [],
    },
    "Exercice de Copenhague (adducteurs)": {
        "pattern_mouvement": "stabilite_hanche",
        "groupe_musculaire_principal": "adducteurs",
        "materiel_requis_liste": ["banc"],
    },
    "Pont fessier (glute bridge)": {
        "pattern_mouvement": "hinge",
        "groupe_musculaire_principal": "fessiers",
        "materiel_requis_liste": [],
    },
    "Gainage dynamique avec rotation": {
        "pattern_mouvement": "rotation",
        "groupe_musculaire_principal": "abdominaux",
        "materiel_requis_liste": [],
    },
    "Équilibre sur une jambe (proprioception)": {
        "pattern_mouvement": "stabilite_hanche",
        "groupe_musculaire_principal": "stabilisateurs",
        "materiel_requis_liste": [],
    },
    "Fente avant (lunge)": {
        "pattern_mouvement": "fente",
        "groupe_musculaire_principal": "jambes",
        "materiel_requis_liste": [],
    },
    "Fente bulgare (pied arrière surélevé)": {
        "pattern_mouvement": "fente",
        "groupe_musculaire_principal": "jambes",
        "materiel_requis_liste": ["banc"],
    },
    "Développé épaules (overhead press)": {
        "pattern_mouvement": "poussee_verticale",
        "groupe_musculaire_principal": "epaules",
        "materiel_requis_liste": ["halteres", "barre"],
    },
    "Tirage vertical (dos)": {
        "pattern_mouvement": "tirage_vertical",
        "groupe_musculaire_principal": "dos",
        "materiel_requis_liste": ["barre_fixe", "machine"],
    },
    "Hip thrust (fessiers)": {
        "pattern_mouvement": "hinge",
        "groupe_musculaire_principal": "fessiers",
        "materiel_requis_liste": ["banc"],
    },
    "Fente arrière déclinée / step-up (force unilatérale jambe)": {
        "pattern_mouvement": "fente",
        "groupe_musculaire_principal": "jambes",
        "materiel_requis_liste": ["banc"],
    },
    "Curl biceps": {
        "pattern_mouvement": "isolation_bras",
        "groupe_musculaire_principal": "biceps",
        "materiel_requis_liste": ["halteres"],
    },
    "Extension triceps": {
        "pattern_mouvement": "isolation_bras",
        "groupe_musculaire_principal": "triceps",
        "materiel_requis_liste": ["halteres"],
    },
    "Élévation latérale (épaules)": {
        "pattern_mouvement": "isolation_epaule",
        "groupe_musculaire_principal": "epaules",
        "materiel_requis_liste": ["halteres"],
    },
    "Relevé de jambes (abdominaux)": {
        "pattern_mouvement": "gainage",
        "groupe_musculaire_principal": "abdominaux",
        "materiel_requis_liste": [],
    },
    "Curl marteau (biceps/avant-bras)": {
        "pattern_mouvement": "isolation_bras",
        "groupe_musculaire_principal": "biceps",
        "materiel_requis_liste": ["halteres"],
    },
    "Écarté couché (pectoraux)": {
        "pattern_mouvement": "poussee_horizontale",
        "groupe_musculaire_principal": "pectoraux",
        "materiel_requis_liste": ["halteres", "banc"],
    },
    "Crunch en vélo (obliques)": {
        "pattern_mouvement": "rotation",
        "groupe_musculaire_principal": "abdominaux",
        "materiel_requis_liste": [],
    },
    "Extension mollets debout": {
        "pattern_mouvement": "isolation_mollet",
        "groupe_musculaire_principal": "mollets",
        "materiel_requis_liste": [],
    },
    "Gammes athlétiques (technique de course)": {
        "pattern_mouvement": "deplacement_agilite",
        "groupe_musculaire_principal": "jambes",
        "materiel_requis_liste": [],
    },
    "Contrôle de balle / jonglage technique": {
        "pattern_mouvement": "technique_ballon",
        "groupe_musculaire_principal": "coordination",
        "materiel_requis_liste": ["ballon"],
    },
    "Mobilité des hanches": {
        "pattern_mouvement": "mobilite",
        "groupe_musculaire_principal": "hanches",
        "materiel_requis_liste": [],
    },
    "Étirements dynamiques jambes (retour au calme)": {
        "pattern_mouvement": "mobilite",
        "groupe_musculaire_principal": "jambes",
        "materiel_requis_liste": [],
    },
    "Mobilité thoracique et épaules": {
        "pattern_mouvement": "mobilite",
        "groupe_musculaire_principal": "epaules",
        "materiel_requis_liste": [],
    },
    "Marche active de récupération": {
        "pattern_mouvement": "mobilite",
        "groupe_musculaire_principal": "corps_entier",
        "materiel_requis_liste": [],
    },
    # --- Enrichissement bibliothèque (21 exercices, cf. audit patterns pauvres) ---
    "Squat poids du corps (air squat)": {
        "pattern_mouvement": "squat",
        "groupe_musculaire_principal": "jambes",
        "materiel_requis_liste": [],
    },
    "Goblet squat": {
        "pattern_mouvement": "squat",
        "groupe_musculaire_principal": "jambes",
        "materiel_requis_liste": ["halteres"],
    },
    "Sumo squat": {
        "pattern_mouvement": "squat",
        "groupe_musculaire_principal": "jambes",
        "materiel_requis_liste": ["barre", "halteres"],
    },
    "Front squat": {
        "pattern_mouvement": "squat",
        "groupe_musculaire_principal": "jambes",
        "materiel_requis_liste": ["barre"],
    },
    "Romanian deadlift (RDL)": {
        "pattern_mouvement": "hinge",
        "groupe_musculaire_principal": "ischio_jambiers",
        "materiel_requis_liste": ["barre", "halteres"],
    },
    "RDL unilatéral haltère": {
        "pattern_mouvement": "hinge",
        "groupe_musculaire_principal": "ischio_jambiers",
        "materiel_requis_liste": ["halteres"],
    },
    "Pompes (push-up)": {
        "pattern_mouvement": "poussee_horizontale",
        "groupe_musculaire_principal": "pectoraux",
        "materiel_requis_liste": [],
    },
    "Pompes inclinées (incline push-up)": {
        "pattern_mouvement": "poussee_horizontale",
        "groupe_musculaire_principal": "pectoraux",
        "materiel_requis_liste": ["banc"],
    },
    "Développé couché haltères": {
        "pattern_mouvement": "poussee_horizontale",
        "groupe_musculaire_principal": "pectoraux",
        "materiel_requis_liste": ["halteres", "banc"],
    },
    "Développé épaules haltères assis": {
        "pattern_mouvement": "poussee_verticale",
        "groupe_musculaire_principal": "epaules",
        "materiel_requis_liste": ["halteres", "banc"],
    },
    "Pike push-up": {
        "pattern_mouvement": "poussee_verticale",
        "groupe_musculaire_principal": "epaules",
        "materiel_requis_liste": [],
    },
    "Push press": {
        "pattern_mouvement": "poussee_verticale",
        "groupe_musculaire_principal": "epaules",
        "materiel_requis_liste": ["barre"],
    },
    "Rowing haltère unilatéral": {
        "pattern_mouvement": "tirage_horizontal",
        "groupe_musculaire_principal": "dos",
        "materiel_requis_liste": ["halteres", "banc"],
    },
    "Rowing inversé (inverted row)": {
        "pattern_mouvement": "tirage_horizontal",
        "groupe_musculaire_principal": "dos",
        "materiel_requis_liste": ["barre_fixe"],
    },
    "Tractions strictes (pull-up)": {
        "pattern_mouvement": "tirage_vertical",
        "groupe_musculaire_principal": "dos",
        "materiel_requis_liste": ["barre_fixe"],
    },
    "Extension mollets unilatérale": {
        "pattern_mouvement": "isolation_mollet",
        "groupe_musculaire_principal": "mollets",
        "materiel_requis_liste": ["halteres"],
    },
    "Extension mollets unilatérale poids du corps": {
        "pattern_mouvement": "isolation_mollet",
        "groupe_musculaire_principal": "mollets",
        "materiel_requis_liste": [],
    },
    "Adduction de hanche au sol": {
        "pattern_mouvement": "stabilite_hanche",
        "groupe_musculaire_principal": "adducteurs",
        "materiel_requis_liste": [],
    },
    "Saut en longueur (broad jump)": {
        "pattern_mouvement": "saut_horizontal",
        "groupe_musculaire_principal": "jambes",
        "materiel_requis_liste": [],
    },
    "Countermovement jump (CMJ)": {
        "pattern_mouvement": "saut_vertical",
        "groupe_musculaire_principal": "jambes",
        "materiel_requis_liste": [],
    },
    "Décélération / réception unilatérale contrôlée": {
        "pattern_mouvement": "deplacement_agilite",
        "groupe_musculaire_principal": "jambes",
        "materiel_requis_liste": [],
    },
}
