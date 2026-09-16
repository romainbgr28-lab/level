"""Tests du contexte compact du coach (coach_contexte.py).

Module pur : tourne sans base, sans FastAPI et sans dépendance tierce.

Ce qu'ils protègent, côté produit : quand l'utilisateur écrit « je fais quoi aujourd'hui ? »,
le coach doit déjà savoir qui il est, ce que prévoit son programme et ce qu'il a réellement
fait — et ne JAMAIS voir une donnée plausible à la place d'une donnée absente.

Lancer avec : python3 -m unittest test_coach_contexte -v (depuis backend/)
"""

import unittest
from datetime import date

import coach_contexte

AUJOURDHUI = date(2026, 9, 16)  # un mercredi


def _profil(**overrides):
    base = {
        "age": 25,
        "taille_cm": 180.0,
        "poids_kg": 75.0,
        "niveau_physique": "intermédiaire",
        "materiel": "Salle complète",
        "objectifs_v2": [
            {"theme": "perte_de_gras", "rang": 1, "poids": 0.6},
            {"theme": "performance_sport_pratique", "rang": 2, "poids": 0.3},
        ],
        "contexte_sportif": {"sport": "football", "frequence_hebdo": 2, "poste": "Milieu"},
        "disponibilites": {
            "lundi": 60, "mardi": None, "mercredi": 60, "jeudi": None,
            "vendredi": 60, "samedi": None, "dimanche": 60,
        },
        "calendrier_matchs": {"jour_habituel": "Samedi", "exceptions": [], "annulations": []},
    }
    base.update(overrides)
    return base


def _contexte_jour(**overrides):
    base = {
        "date": AUJOURDHUI,
        "jour_abbrev": "Mer",
        "jour_label": "Mercredi",
        "statut": "seance",
        "type_seance_prevu": "force",
        "phase_calendaire": "phase_normale",
        "semaine_programme": 2,
        "phase_nom": "Fondation",
        "phase_description": "Construire la base",
        "prochaine_seance": None,
    }
    base.update(overrides)
    return base


class TestConstruireContexte(unittest.TestCase):
    def test_contexte_complet(self):
        contexte = coach_contexte.construire_contexte(
            profil=_profil(),
            programme={"duree_semaines": 8, "gabarit_hebdomadaire": {"Mer": "force"}},
            contexte_jour=_contexte_jour(),
            seance_du_jour={
                "id": 7,
                "nom": "Haut du corps",
                "statut": "planifiee",
                "duree_prevue": 42,
                "exercices": [
                    {"exercice_id": 1, "nom": "Développé incliné", "series": 4,
                     "repetitions": "8", "charge_indicative": "24 kg"}
                ],
            },
            historique_recent=[],
            contextes_signales=[],
            aujourdhui=AUJOURDHUI,
        )

        self.assertEqual(contexte["profil"]["age"], 25)
        self.assertEqual(contexte["jour"]["statut"], "seance")
        self.assertEqual(contexte["programme"]["semaine_courante"], 2)
        self.assertEqual(contexte["seance_du_jour"]["id"], 7)
        self.assertEqual(contexte["objectifs"][0]["label"], "perte de gras")

    def test_frequence_du_sport_n_est_pas_le_nombre_de_seances_level(self):
        """Règle métier existante (user_model_v2) : frequence_hebdo décrit le SPORT pratiqué.
        Le nom de clé exposé au modèle doit le dire, sinon le coach peut le confondre avec le
        nombre de séances LEVEL et raisonner faux sur toute la semaine."""
        contexte = coach_contexte.construire_contexte(
            profil=_profil(), programme=None, contexte_jour=_contexte_jour(),
            seance_du_jour=None, historique_recent=[], contextes_signales=[], aujourdhui=AUJOURDHUI,
        )

        self.assertEqual(contexte["profil"]["frequence_hebdo_sport"], 2)
        self.assertNotIn("frequence_hebdo", contexte["profil"])

    def test_sans_profil_aucune_donnee_inventee(self):
        contexte = coach_contexte.construire_contexte(
            profil=None, programme=None, contexte_jour=_contexte_jour(statut="aucun_profil"),
            seance_du_jour=None, historique_recent=[], contextes_signales=[], aujourdhui=AUJOURDHUI,
        )

        self.assertIsNone(contexte["profil"])
        self.assertEqual(contexte["objectifs"], [])
        self.assertIsNone(contexte["materiel"])
        self.assertIsNone(contexte["seance_du_jour"])

    def test_historique_borne(self):
        """Le contexte reste compact : au-delà de la limite, le coach doit appeler une action
        plutôt que recevoir toute la base d'avance."""
        historique = [
            {"date": f"2026-09-{jour:02d}", "type_seance": "force", "rpe": 7,
             "pourcentage_complete": 100.0, "exercices_realises": []}
            for jour in range(1, 15)
        ]

        contexte = coach_contexte.construire_contexte(
            profil=_profil(), programme=None, contexte_jour=_contexte_jour(),
            seance_du_jour=None, historique_recent=historique, contextes_signales=[],
            aujourdhui=AUJOURDHUI,
        )

        self.assertEqual(len(contexte["historique_recent"]), coach_contexte.MAX_SEANCES_HISTORIQUE)

    def test_contraintes_actives_reprises(self):
        contexte = coach_contexte.construire_contexte(
            profil=_profil(), programme=None, contexte_jour=_contexte_jour(),
            seance_du_jour=None, historique_recent=[],
            contextes_signales=[
                {"type": "douleur", "valeur": "épaules", "details": "gêne au développé",
                 "date_debut": "2026-09-14", "date_fin": "2026-09-28"}
            ],
            aujourdhui=AUJOURDHUI,
        )

        self.assertEqual(len(contexte["contraintes_actives"]), 1)
        self.assertEqual(contexte["contraintes_actives"][0]["valeur"], "épaules")


class TestFormatagePrompt(unittest.TestCase):
    def test_contient_les_faits_utiles(self):
        contexte = coach_contexte.construire_contexte(
            profil=_profil(),
            programme={"duree_semaines": 8, "gabarit_hebdomadaire": {"Mer": "force"}},
            contexte_jour=_contexte_jour(),
            seance_du_jour={
                "id": 7, "nom": "Haut du corps", "statut": "planifiee", "duree_prevue": 42,
                "exercices": [{"exercice_id": 1, "nom": "Développé incliné", "series": 4,
                               "repetitions": "8", "charge_indicative": "24 kg"}],
            },
            historique_recent=[
                {"date": "2026-09-14", "type_seance": "force", "rpe": 6,
                 "pourcentage_complete": 100.0,
                 "exercices_realises": [{"exercice_id": 1, "nom": "Développé incliné"}]}
            ],
            contextes_signales=[],
            aujourdhui=AUJOURDHUI,
        )

        texte = coach_contexte.formater_pour_prompt(contexte)

        self.assertIn("2026-09-16", texte)
        self.assertIn("Développé incliné", texte)
        self.assertIn("semaine 2/8", texte)
        self.assertIn("Samedi", texte)  # jour de match habituel
        self.assertIn("id=7", texte)

    def test_dit_explicitement_ce_qui_manque(self):
        """Une donnée absente doit se lire comme absente : sinon le modèle comble le silence."""
        contexte = coach_contexte.construire_contexte(
            profil=None, programme=None, contexte_jour=_contexte_jour(statut="aucun_profil"),
            seance_du_jour=None, historique_recent=[], contextes_signales=[], aujourdhui=AUJOURDHUI,
        )

        texte = coach_contexte.formater_pour_prompt(contexte)

        self.assertIn("aucun profil enregistré", texte)
        self.assertIn("PROGRAMME ACTIF : aucun.", texte)
        self.assertIn("aucune séance encore générée", texte)
        self.assertIn("aucune séance terminée", texte)

    def test_jour_de_match_visible(self):
        contexte = coach_contexte.construire_contexte(
            profil=_profil(), programme={"duree_semaines": 8, "gabarit_hebdomadaire": {}},
            contexte_jour=_contexte_jour(statut="match", type_seance_prevu=None),
            seance_du_jour=None, historique_recent=[], contextes_signales=[], aujourdhui=AUJOURDHUI,
        )

        self.assertIn("jour de match", coach_contexte.formater_pour_prompt(contexte))


if __name__ == "__main__":
    unittest.main()
