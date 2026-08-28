"""Tests unitaires — Moteur d'Adaptation LEVEL v2, Étape 5 : bloc de prompt par exercice
(moteur_decision.formater_section_prompt / _formater_bloc_par_exercice).

Ne touche à aucun calcul de charge/volume/persistance : vérifie uniquement que le texte du
prompt reflète fidèlement ce que DecisionCoaching.par_exercice contient déjà (Étape 4), avec
repli complet vers le comportement actuel quand par_exercice est vide.

Lancer avec : python3 -m unittest test_prompt_par_exercice -v (depuis backend/)
"""

import unittest
from datetime import date, timedelta

import moteur_decision

PROFIL_MINIMAL = {
    "poste": "",
    "niveau_physique": "intermediaire",
    "materiel": "",
    "objectifs_v2": [],
    "contexte_sportif": {},
    "disponibilites": {},
    "objectif_esthetique": None,
    "calendrier_matchs": None,
}

ETAT_DU_JOUR_MINIMAL = {
    "sommeil": "bien",
    "motivation": "bien",
    "temps_dispo": "45 min",
    "envie_texte": "",
    "entrainement_club_semaine": 0,
}


def _historique_vide():
    return {"par_type": {}, "recent": [], "zones_sensibles_recentes": []}


def _occurrence(exercice_id, reps_prevues=10, repetitions=10, rpe=6.0, poids_kg=50.0, charge_prevue_kg=50.0, nom=None):
    return {
        "exercice_id": exercice_id,
        "nom": nom,
        "series": [
            {
                "numero_serie": 1,
                "poids_kg": poids_kg,
                "repetitions": repetitions,
                "reps_prevues": reps_prevues,
                "charge_prevue_kg": charge_prevue_kg,
                "rpe_approx": rpe,
            }
        ],
    }


def _seance(jours_avant, exercices_realises, today):
    return {
        "date": today - timedelta(days=jours_avant),
        "rpe": 6,
        "pourcentage_complete": 100,
        "exercices_realises": exercices_realises,
    }


def _historique_avec_seances(seances, type_seance="force"):
    return {"par_type": {type_seance: seances[:3]}, "recent": seances[:3], "zones_sensibles_recentes": []}


class TestFallbackSansParExercice(unittest.TestCase):
    """Sans exercices_seance (aucun appelant existant ne le passe), le texte du prompt doit
    rester STRICTEMENT identique à avant l'Étape 5 -- aucune ligne "CHARGES CIBLES PAR
    EXERCICE" ne doit apparaître."""

    def test_texte_inchange_sans_exercices_seance(self):
        decision = moteur_decision.construire_decision(
            PROFIL_MINIMAL, _historique_vide(), ETAT_DU_JOUR_MINIMAL, aujourdhui=date.today()
        )
        section = moteur_decision.formater_section_prompt(decision)
        self.assertNotIn("CHARGES CIBLES PAR EXERCICE", section)
        self.assertIn("VOICI LA DÉCISION DU COACH", section)
        self.assertIn("Raisons de cette décision", section)  # fin du texte existant intacte

    def test_texte_inchange_avec_exercices_seance_vide(self):
        decision = moteur_decision.construire_decision(
            PROFIL_MINIMAL, _historique_vide(), ETAT_DU_JOUR_MINIMAL, aujourdhui=date.today(), exercices_seance=[],
        )
        section = moteur_decision.formater_section_prompt(decision)
        self.assertNotIn("CHARGES CIBLES PAR EXERCICE", section)

    def test_texte_identique_octet_pres_avec_et_sans_par_exercice_vide(self):
        d1 = moteur_decision.construire_decision(
            PROFIL_MINIMAL, _historique_vide(), ETAT_DU_JOUR_MINIMAL, aujourdhui=date.today()
        )
        d2 = moteur_decision.construire_decision(
            PROFIL_MINIMAL, _historique_vide(), ETAT_DU_JOUR_MINIMAL, aujourdhui=date.today(), exercices_seance=[],
        )
        self.assertEqual(
            moteur_decision.formater_section_prompt(d1),
            moteur_decision.formater_section_prompt(d2),
        )


class TestBlocParExercicePresent(unittest.TestCase):
    def test_bloc_present_quand_par_exercice_non_vide(self):
        today = date.today()
        seances = [_seance(3, [_occurrence(1, rpe=4.0, nom="Développé couché")], today)]
        historique = _historique_avec_seances(seances)
        decision = moteur_decision.construire_decision(
            PROFIL_MINIMAL, historique, ETAT_DU_JOUR_MINIMAL, aujourdhui=today,
            exercices_seance=[{"exercice_id": 1, "nom": "Développé couché", "charge_reference_kg": 50.0, "series_cible": 3}],
        )
        section = moteur_decision.formater_section_prompt(decision)

        self.assertIn("CHARGES CIBLES PAR EXERCICE", section)
        self.assertIn("Ne pas la recalculer. Ne pas proposer une autre charge.", section)
        self.assertIn("Développé couché (id 1)", section)
        self.assertIn("charge cible : 52.5 kg", section)  # 50 * 1.05 (cas A, +5%)
        self.assertIn("ajustement : +5%", section)
        self.assertIn("séries : 3", section)
        self.assertIn("raison : ", section)  # la raison de la composition est bien reprise dans le texte

    def test_bloc_reflete_exactement_par_exercice(self):
        today = date.today()
        seances = [_seance(3, [_occurrence(1, repetitions=6, rpe=9.0, nom="Curl")], today)]
        historique = _historique_avec_seances(seances)
        decision = moteur_decision.construire_decision(
            PROFIL_MINIMAL, historique, ETAT_DU_JOUR_MINIMAL, aujourdhui=today,
            exercices_seance=[{"exercice_id": 1, "nom": "Curl", "charge_reference_kg": 12.0, "series_cible": 2}],
        )
        section = moteur_decision.formater_section_prompt(decision)
        item = decision.par_exercice[1]

        # Pas d'écart entre la valeur calculée (source de vérité) et ce qui apparaît dans le texte.
        self.assertIn(f"ajustement : {item['charge_pct']:+.0f}%", section)
        self.assertIn(f"charge cible : {item['charge_cible_kg']:.1f} kg", section)
        self.assertIn(item["raison"], section)

    def test_exercice_sans_charge_reference_affiche_repli_explicite(self):
        today = date.today()
        decision = moteur_decision.construire_decision(
            PROFIL_MINIMAL, _historique_vide(), ETAT_DU_JOUR_MINIMAL, aujourdhui=today,
            exercices_seance=[{"exercice_id": 7, "nom": "Squat gobelet"}],  # jamais réalisé, pas de charge_reference_kg
        )
        section = moteur_decision.formater_section_prompt(decision)
        self.assertIn("Squat gobelet (id 7)", section)
        self.assertIn("à définir selon la charge de départ", section)
        self.assertNotIn("None kg", section)  # jamais une valeur brute non formatée

    def test_exercice_sans_nom_utilise_repli_sur_id(self):
        today = date.today()
        decision = moteur_decision.construire_decision(
            PROFIL_MINIMAL, _historique_vide(), ETAT_DU_JOUR_MINIMAL, aujourdhui=today,
            exercices_seance=[{"exercice_id": 99}],
        )
        section = moteur_decision.formater_section_prompt(decision)
        self.assertIn("Exercice #99 (id 99)", section)

    def test_plusieurs_exercices_ordre_deterministe_par_id(self):
        today = date.today()
        decision = moteur_decision.construire_decision(
            PROFIL_MINIMAL, _historique_vide(), ETAT_DU_JOUR_MINIMAL, aujourdhui=today,
            exercices_seance=[{"exercice_id": 5, "nom": "Rowing"}, {"exercice_id": 2, "nom": "Bench"}],
        )
        section = moteur_decision.formater_section_prompt(decision)
        self.assertLess(section.index("Bench (id 2)"), section.index("Rowing (id 5)"))


class TestFormaterBlocParExerciceDirect(unittest.TestCase):
    """Tests directs de _formater_bloc_par_exercice, sans passer par construire_decision, pour
    isoler strictement le formatage du reste du pipeline."""

    def test_dict_vide_retourne_chaine_vide(self):
        self.assertEqual(moteur_decision._formater_bloc_par_exercice({}), "")

    def test_valeurs_affichees_sans_aucun_ecart_avec_lentree(self):
        par_exercice = {
            12: {
                "exercice_id": 12, "nom": "Bench", "charge_pct": 5.0, "volume_pct": 0.0,
                "charge_cible_kg": 82.5, "series_cible": 3, "raison": "progression maîtrisée",
                "confiance": 0.6, "source": "adaptation_exercice", "garde_fou_applique": None,
                "decision_exercice": None,
            }
        }
        texte = moteur_decision._formater_bloc_par_exercice(par_exercice)
        self.assertIn("Bench (id 12)", texte)
        self.assertIn("charge cible : 82.5 kg", texte)
        self.assertIn("ajustement : +5%", texte)
        self.assertIn("séries : 3", texte)
        self.assertIn("raison : progression maîtrisée", texte)


if __name__ == "__main__":
    unittest.main()
