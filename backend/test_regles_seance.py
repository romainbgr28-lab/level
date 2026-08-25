"""Tests unitaires du moteur d'adaptation de charge (calculer_ajustement_charge).

Lancer avec : python3 -m unittest backend.test_regles_seance -v
(ou, depuis backend/ : python3 -m unittest test_regles_seance -v)
"""

import unittest
from datetime import date, timedelta

from regles_seance import calculer_ajustement_charge

AUJOURDHUI = date(2026, 8, 25)


def _s(jours_avant: int, rpe, pourcentage):
    return {
        "date": AUJOURDHUI - timedelta(days=jours_avant),
        "rpe": rpe,
        "pourcentage_complete": pourcentage,
    }


class TestCalculerAjustementCharge(unittest.TestCase):
    # 0. Historique vide
    def test_historique_vide(self):
        r = calculer_ajustement_charge([], "intermédiaire", AUJOURDHUI)
        self.assertEqual(r["charge_pct"], 0.0)
        self.assertEqual(r["volume_pct"], 0.0)
        self.assertIn("onboarding", r["raison"])

    # 1. > 10 jours
    def test_plus_de_10_jours(self):
        historique = [_s(15, 5, 100)]
        r = calculer_ajustement_charge(historique, aujourdhui=AUJOURDHUI)
        self.assertEqual(r["charge_pct"], -15.0)
        self.assertEqual(r["volume_pct"], 0.0)
        self.assertIn("15 jours", r["raison"])

    def test_10_jours_pile_pas_de_declenchement(self):
        # jours_ecart == 10 ne doit pas déclencher la règle de reprise (strictement > 10)
        historique = [_s(10, 6, 95)]
        r = calculer_ajustement_charge(historique, aujourdhui=AUJOURDHUI)
        self.assertNotEqual(r["charge_pct"], -15.0)

    # 2. 3 séances difficiles -> décharge
    def test_trois_seances_difficiles_decharge(self):
        historique = [_s(2, 9, 100), _s(9, 8, 60), _s(16, 8, 100)]
        r = calculer_ajustement_charge(historique, aujourdhui=AUJOURDHUI)
        self.assertEqual(r["charge_pct"], -15.0)
        self.assertEqual(r["volume_pct"], -20.0)
        self.assertIn("décharge", r["raison"])

    # 3. RPE 9 + complétion 100% -> réduction quand même
    def test_rpe_9_completion_100(self):
        historique = [_s(2, 9, 100)]
        r = calculer_ajustement_charge(historique, aujourdhui=AUJOURDHUI)
        self.assertEqual(r["charge_pct"], -10.0)
        self.assertEqual(r["volume_pct"], -12.0)
        self.assertIn("RPE 9", r["raison"])

    def test_rpe_10(self):
        historique = [_s(2, 10, 80)]
        r = calculer_ajustement_charge(historique, aujourdhui=AUJOURDHUI)
        self.assertEqual(r["charge_pct"], -10.0)
        self.assertEqual(r["volume_pct"], -12.0)

    def test_rpe_8_seul(self):
        historique = [_s(2, 8, 95)]
        r = calculer_ajustement_charge(historique, aujourdhui=AUJOURDHUI)
        self.assertEqual(r["charge_pct"], -5.0)
        self.assertEqual(r["volume_pct"], -5.0)

    # 4. RPE 5 + complétion 60% -> pas de progression
    def test_rpe_5_completion_60(self):
        historique = [_s(2, 5, 60)]
        r = calculer_ajustement_charge(historique, aujourdhui=AUJOURDHUI)
        self.assertEqual(r["charge_pct"], -5.0)
        self.assertEqual(r["volume_pct"], -10.0)
        self.assertIn("60%", r["raison"])
        self.assertNotIn("bien maîtrisée", r["raison"])

    # 5. 3 séances faciles -> progression modérée
    def test_trois_seances_faciles_progression_moderee(self):
        historique = [_s(2, 4, 100), _s(9, 5, 95), _s(16, 5, 90)]
        r = calculer_ajustement_charge(historique, aujourdhui=AUJOURDHUI)
        self.assertEqual(r["charge_pct"], 8.0)
        self.assertEqual(r["volume_pct"], 5.0)

    # 6. 2 séances maîtrisées -> progression légère
    def test_deux_seances_maitrisees_progression_legere(self):
        historique = [_s(2, 5, 100), _s(9, 6, 95)]
        r = calculer_ajustement_charge(historique, aujourdhui=AUJOURDHUI)
        self.assertEqual(r["charge_pct"], 5.0)
        self.assertEqual(r["volume_pct"], 0.0)

    # 7. Une seule séance RPE 5 / 100% -> maintien + signal positif, pas de hausse
    def test_une_seule_seance_facile_maintien_signal_positif(self):
        historique = [_s(2, 5, 100)]
        r = calculer_ajustement_charge(historique, aujourdhui=AUJOURDHUI)
        self.assertEqual(r["charge_pct"], 0.0)
        self.assertEqual(r["volume_pct"], 0.0)
        self.assertIn("bon signal", r["raison"])

    # 8. Cas neutre : RPE 6-7, complétion correcte -> maintien
    def test_cas_neutre_maintien(self):
        historique = [_s(2, 7, 85)]
        r = calculer_ajustement_charge(historique, aujourdhui=AUJOURDHUI)
        self.assertEqual(r["charge_pct"], 0.0)
        self.assertEqual(r["volume_pct"], 0.0)

    def test_donnees_manquantes_maintien(self):
        historique = [_s(2, None, None)]
        r = calculer_ajustement_charge(historique, aujourdhui=AUJOURDHUI)
        self.assertEqual(r["charge_pct"], 0.0)
        self.assertEqual(r["volume_pct"], 0.0)

    # Déterminisme : même input -> même output
    def test_determinisme(self):
        historique = [_s(2, 5, 100), _s(9, 6, 95)]
        r1 = calculer_ajustement_charge(list(historique), "intermédiaire", AUJOURDHUI)
        r2 = calculer_ajustement_charge(list(historique), "intermédiaire", AUJOURDHUI)
        self.assertEqual(r1, r2)

    # L'ordre de la liste d'entrée ne doit pas influencer le résultat (tri interne par date).
    def test_ordre_entree_indifferent(self):
        historique = [_s(2, 5, 100), _s(9, 6, 95)]
        r_ordre_1 = calculer_ajustement_charge(historique, aujourdhui=AUJOURDHUI)
        r_ordre_2 = calculer_ajustement_charge(list(reversed(historique)), aujourdhui=AUJOURDHUI)
        self.assertEqual(r_ordre_1, r_ordre_2)


if __name__ == "__main__":
    unittest.main()
