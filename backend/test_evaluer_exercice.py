"""Tests unitaires — Moteur d'Adaptation LEVEL v2, Étape 2 : matrice de décision par exercice
(adaptation_exercice.evaluer_exercice). Fonctions pures, sans FastAPI/SQLAlchemy.

Lancer avec : python3 -m unittest test_evaluer_exercice -v (depuis backend/)
"""

import unittest
from datetime import date

from adaptation_exercice import (
    CONFIANCE_HAUTE,
    CONFIANCE_MOYENNE,
    HistoriqueExercice,
    OccurrenceExercice,
    _plafonner_charge_pct,
    evaluer_exercice,
)


def _serie(numero=1, poids_kg=20.0, repetitions=10, reps_prevues=10, charge_prevue_kg=20.0, rpe_approx=5):
    return {
        "numero_serie": numero,
        "poids_kg": poids_kg,
        "repetitions": repetitions,
        "reps_prevues": reps_prevues,
        "charge_prevue_kg": charge_prevue_kg,
        "rpe_approx": rpe_approx,
    }


def _occurrence(jour="2026-08-20", series=None):
    return OccurrenceExercice(date=date.fromisoformat(jour), exercice_id=1, series=series or [_serie()])


def _historique(occurrences):
    return HistoriqueExercice(exercice_id=1, occurrences=occurrences, jamais_realise=not occurrences)


class TestJamaisRealise(unittest.TestCase):
    def test_decision_neutre_par_defaut(self):
        d = evaluer_exercice(_historique([]))
        self.assertEqual(d.charge_pct, 0.0)
        self.assertEqual(d.volume_pct, 0.0)
        self.assertEqual(d.confiance, 0.0)
        self.assertEqual(d.source, "defaut")
        self.assertEqual(d.raison, "première fois")
        self.assertEqual(d.regle_gagnante, "jamais_realise")


class TestCasA(unittest.TestCase):
    def test_reps_atteintes_charge_stable_rpe_bas(self):
        occ = _occurrence(series=[_serie(repetitions=10, reps_prevues=10, poids_kg=20, charge_prevue_kg=20, rpe_approx=4)])
        d = evaluer_exercice(_historique([occ]))
        self.assertEqual(d.regle_gagnante, "A")
        self.assertEqual(d.charge_pct, 5.0)
        self.assertEqual(d.volume_pct, 0.0)


class TestCasB(unittest.TestCase):
    def test_reps_atteintes_charge_stable_rpe_haut(self):
        occ = _occurrence(series=[_serie(repetitions=10, reps_prevues=10, poids_kg=20, charge_prevue_kg=20, rpe_approx=9)])
        d = evaluer_exercice(_historique([occ]))
        self.assertEqual(d.regle_gagnante, "B")
        self.assertEqual(d.charge_pct, 0.0)


class TestCasC(unittest.TestCase):
    def test_reps_intermediaire_rpe_bas_pas_de_sanction(self):
        # 8/10 = 0.8 -> zone intermédiaire [0.75, 0.95)
        occ = _occurrence(series=[_serie(repetitions=8, reps_prevues=10, rpe_approx=4)])
        d = evaluer_exercice(_historique([occ]))
        self.assertEqual(d.regle_gagnante, "C")
        self.assertEqual(d.charge_pct, 0.0)
        self.assertEqual(d.volume_pct, 0.0)


class TestCasD(unittest.TestCase):
    def test_reps_non_atteintes_rpe_eleve_echec_reel(self):
        occ = _occurrence(series=[_serie(repetitions=6, reps_prevues=10, rpe_approx=9)])
        d = evaluer_exercice(_historique([occ]))
        self.assertEqual(d.regle_gagnante, "D")
        self.assertEqual(d.charge_pct, -8.0)

    def test_confiance_haute_si_confirme_par_occurrence_precedente(self):
        occ_recente = _occurrence(jour="2026-08-20", series=[_serie(repetitions=6, reps_prevues=10, rpe_approx=9)])
        occ_precedente = _occurrence(jour="2026-08-13", series=[_serie(repetitions=7, reps_prevues=10, rpe_approx=8)])
        d = evaluer_exercice(_historique([occ_recente, occ_precedente]))
        self.assertEqual(d.regle_gagnante, "D")
        self.assertEqual(d.confiance, CONFIANCE_HAUTE)


class TestCasE(unittest.TestCase):
    def test_ratio_superieur_a_1_05_rpe_bas(self):
        # 12/10 = 1.2 > 1.05, charge inchangée -> Cas E, pas F.
        occ = _occurrence(series=[_serie(repetitions=12, reps_prevues=10, poids_kg=20, charge_prevue_kg=20, rpe_approx=4)])
        d = evaluer_exercice(_historique([occ]))
        self.assertEqual(d.regle_gagnante, "E")
        self.assertEqual(d.charge_pct, 5.0)


class TestCasF(unittest.TestCase):
    def test_charge_reellement_superieure_devient_reference(self):
        # Exemple exact de la mission : prévu 40kg, réel 42.5kg (+6.25%), reps atteintes.
        occ = _occurrence(series=[_serie(repetitions=10, reps_prevues=10, poids_kg=42.5, charge_prevue_kg=40.0, rpe_approx=5)])
        d = evaluer_exercice(_historique([occ]))
        self.assertEqual(d.regle_gagnante, "F")
        self.assertEqual(d.charge_pct, 5.0)  # plafonné à +5%, jamais 5% + 6.25% cumulés
        self.assertIn("nouvelle référence", d.raison)

    def test_delta_charge_exactement_seuil_ne_declenche_pas_f(self):
        # +2.5% pile : la spec exige "> +2.5%" (strictement supérieur), donc pas F ici.
        occ = _occurrence(series=[_serie(repetitions=10, reps_prevues=10, poids_kg=20.5, charge_prevue_kg=20.0, rpe_approx=4)])
        d = evaluer_exercice(_historique([occ]))
        self.assertNotEqual(d.regle_gagnante, "F")
        self.assertEqual(d.regle_gagnante, "A")  # charge jugée équivalente (delta <= 2.5%)


class TestCasG(unittest.TestCase):
    def test_charge_reelle_inferieure_rpe_eleve(self):
        occ = _occurrence(series=[_serie(repetitions=10, reps_prevues=10, poids_kg=17.0, charge_prevue_kg=20.0, rpe_approx=9)])
        d = evaluer_exercice(_historique([occ]))
        self.assertEqual(d.regle_gagnante, "G")
        self.assertEqual(d.charge_pct, -5.0)


class TestCasH(unittest.TestCase):
    def test_evaluation_independante_des_autres_exercices(self):
        # evaluer_exercice() ne reçoit QUE l'historique de l'exercice concerné : aucune donnée
        # d'un autre exercice de la séance ne peut donc jamais influencer sa décision. On le
        # démontre en évaluant "Curl" (échec, cas D) et "Bench" (réussite, cas A) séparément :
        # rien dans la signature de la fonction ne permet à l'un de contaminer l'autre.
        curl = _historique([_occurrence(series=[_serie(repetitions=6, reps_prevues=10, rpe_approx=9)])])
        bench = _historique([_occurrence(series=[_serie(repetitions=10, reps_prevues=10, poids_kg=20, charge_prevue_kg=20, rpe_approx=4)])])

        d_curl = evaluer_exercice(curl)
        d_bench = evaluer_exercice(bench)

        self.assertEqual(d_curl.regle_gagnante, "D")
        self.assertEqual(d_curl.charge_pct, -8.0)
        self.assertEqual(d_bench.regle_gagnante, "A")
        self.assertEqual(d_bench.charge_pct, 5.0)


class TestSeuilsExacts(unittest.TestCase):
    def test_ratio_exactement_0_95_est_considere_atteint(self):
        occ = _occurrence(series=[_serie(repetitions=19, reps_prevues=20, poids_kg=20, charge_prevue_kg=20, rpe_approx=4)])
        d = evaluer_exercice(_historique([occ]))
        self.assertEqual(d.regle_gagnante, "A")  # 0.95 pile -> "reps atteintes", pas zone intermédiaire

    def test_ratio_exactement_0_75_est_zone_intermediaire(self):
        occ = _occurrence(series=[_serie(repetitions=3, reps_prevues=4, rpe_approx=4)])  # 0.75 pile
        d = evaluer_exercice(_historique([occ]))
        self.assertEqual(d.regle_gagnante, "C")

    def test_rpe_exactement_8_est_haut(self):
        occ = _occurrence(series=[_serie(repetitions=10, reps_prevues=10, poids_kg=20, charge_prevue_kg=20, rpe_approx=8)])
        d = evaluer_exercice(_historique([occ]))
        self.assertEqual(d.regle_gagnante, "B")

    def test_rpe_exactement_5_est_bas(self):
        occ = _occurrence(series=[_serie(repetitions=10, reps_prevues=10, poids_kg=20, charge_prevue_kg=20, rpe_approx=5)])
        d = evaluer_exercice(_historique([occ]))
        self.assertEqual(d.regle_gagnante, "A")


class TestConfiance(unittest.TestCase):
    def test_occurrence_unique_jamais_haute(self):
        occ = _occurrence(series=[_serie(repetitions=10, reps_prevues=10, poids_kg=20, charge_prevue_kg=20, rpe_approx=4)])
        d = evaluer_exercice(_historique([occ]))
        self.assertLess(d.confiance, CONFIANCE_HAUTE)
        self.assertEqual(d.confiance, CONFIANCE_MOYENNE)

    def test_plusieurs_occurrences_cohérentes_confiance_haute(self):
        occ1 = _occurrence(jour="2026-08-20", series=[_serie(repetitions=10, reps_prevues=10, poids_kg=20, charge_prevue_kg=20, rpe_approx=4)])
        occ2 = _occurrence(jour="2026-08-13", series=[_serie(repetitions=10, reps_prevues=10, poids_kg=20, charge_prevue_kg=20, rpe_approx=5)])
        d = evaluer_exercice(_historique([occ1, occ2]))
        self.assertEqual(d.confiance, CONFIANCE_HAUTE)

    def test_occurrences_incohérentes_confiance_reste_moyenne(self):
        occ1 = _occurrence(jour="2026-08-20", series=[_serie(repetitions=10, reps_prevues=10, poids_kg=20, charge_prevue_kg=20, rpe_approx=4)])
        occ2 = _occurrence(jour="2026-08-13", series=[_serie(repetitions=6, reps_prevues=10, rpe_approx=9)])
        d = evaluer_exercice(_historique([occ1, occ2]))
        self.assertEqual(d.confiance, CONFIANCE_MOYENNE)


class TestAbsenceDeSignal(unittest.TestCase):
    def test_absence_signal_reps(self):
        occ = _occurrence(series=[_serie(reps_prevues=None, rpe_approx=4)])
        d = evaluer_exercice(_historique([occ]))
        signal_reps = next(s for s in d.signaux if s.type == "ratio_reps")
        self.assertIsNone(signal_reps.valeur)
        self.assertLess(d.confiance, CONFIANCE_MOYENNE + 0.01)
        self.assertEqual(d.regle_gagnante, "neutre")  # aucune branche ne peut trancher sans ratio

    def test_absence_signal_rpe(self):
        occ = _occurrence(series=[_serie(reps_prevues=10, repetitions=10, rpe_approx=None)])
        d = evaluer_exercice(_historique([occ]))
        signal_rpe = next(s for s in d.signaux if s.type == "rpe_exercice")
        self.assertIsNone(signal_rpe.valeur)
        self.assertNotEqual(d.confiance, CONFIANCE_HAUTE)


class TestPlafond(unittest.TestCase):
    def test_plafonner_charge_pct_borne_haute(self):
        self.assertEqual(_plafonner_charge_pct(15.0), 10.0)

    def test_plafonner_charge_pct_borne_basse(self):
        self.assertEqual(_plafonner_charge_pct(-20.0), -10.0)

    def test_plafonner_charge_pct_valeur_normale_inchangee(self):
        self.assertEqual(_plafonner_charge_pct(5.0), 5.0)

    def test_aucun_cas_de_la_matrice_ne_depasse_le_plafond(self):
        cas = [
            _occurrence(series=[_serie(repetitions=10, reps_prevues=10, poids_kg=25, charge_prevue_kg=20, rpe_approx=4)]),  # F
            _occurrence(series=[_serie(repetitions=6, reps_prevues=10, rpe_approx=9)]),  # D
        ]
        for occ in cas:
            d = evaluer_exercice(_historique([occ]))
            self.assertLessEqual(d.charge_pct, 10.0)
            self.assertGreaterEqual(d.charge_pct, -10.0)


if __name__ == "__main__":
    unittest.main()
