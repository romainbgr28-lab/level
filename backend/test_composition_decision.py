"""Tests unitaires — Moteur d'Adaptation LEVEL v2, Étape 3 : composition séance + exercice
(composition_decision.composer). Fonctions pures, sans FastAPI/SQLAlchemy.

Lancer avec : python3 -m unittest test_composition_decision -v (depuis backend/)
"""

import unittest

from adaptation_exercice import DecisionExercice
from composition_decision import PLAFOND_FATIGUE_PCT, DecisionSeance, composer


def _decision_exercice(exercice_id, charge_pct, regle="A", confiance=0.6):
    return DecisionExercice(
        exercice_id=exercice_id,
        charge_pct=charge_pct,
        volume_pct=0.0,
        raison=f"cas {regle}",
        confiance=confiance,
        source="adaptation_exercice",
        signaux=[],
        regle_gagnante=regle,
    )


def _decision_seance(deload_actif=False, fatigue_globale="normale", charge_pct=0.0, volume_global_pct=0.0):
    return DecisionSeance(
        type_seance="force",
        intensite_max="normale",
        deload_actif=deload_actif,
        fatigue_globale=fatigue_globale,
        jours_ecart=3,
        volume_global_pct=volume_global_pct,
        charge_pct=charge_pct,
        exclusions=[],
        raisons=[],
        confiance=0.7,
        source="regles_seance",
    )


class TestCas1SeanceNormale(unittest.TestCase):
    def test_bench_rowing_curl_inchanges(self):
        seance = _decision_seance()
        bench = composer(seance, _decision_exercice(1, 5.0, "A"), exercice_id=1)
        rowing = composer(seance, _decision_exercice(2, 5.0, "A"), exercice_id=2)
        curl = composer(seance, _decision_exercice(3, -8.0, "D"), exercice_id=3)

        self.assertEqual(bench.charge_pct, 5.0)
        self.assertEqual(rowing.charge_pct, 5.0)
        self.assertEqual(curl.charge_pct, -8.0)
        self.assertIsNone(bench.garde_fou_applique)
        self.assertIsNone(curl.garde_fou_applique)


class TestCas2FatigueGlobale(unittest.TestCase):
    def test_progressions_plafonnees_regression_inchangee(self):
        seance = _decision_seance(fatigue_globale="elevee")
        bench = composer(seance, _decision_exercice(1, 5.0, "A"), exercice_id=1)
        rowing = composer(seance, _decision_exercice(2, 5.0, "A"), exercice_id=2)
        curl = composer(seance, _decision_exercice(3, -8.0, "D"), exercice_id=3)

        self.assertEqual(bench.charge_pct, PLAFOND_FATIGUE_PCT)
        self.assertEqual(rowing.charge_pct, PLAFOND_FATIGUE_PCT)
        self.assertEqual(curl.charge_pct, -8.0)  # jamais adoucie
        self.assertEqual(bench.garde_fou_applique, "plafond_fatigue")
        self.assertIsNone(curl.garde_fou_applique)  # rien n'a changé pour lui, pas de garde-fou signalé


class TestCas3Deload(unittest.TestCase):
    def test_deload_ecrase_toutes_les_decisions(self):
        seance = _decision_seance(deload_actif=True, charge_pct=-15.0, volume_global_pct=-20.0)
        bench = composer(seance, _decision_exercice(1, 5.0, "A"), exercice_id=1)
        rowing = composer(seance, _decision_exercice(2, 5.0, "A"), exercice_id=2)
        curl = composer(seance, _decision_exercice(3, -8.0, "D"), exercice_id=3)

        self.assertEqual(bench.charge_pct, -15.0)
        self.assertEqual(rowing.charge_pct, -15.0)
        self.assertEqual(curl.charge_pct, -15.0)
        self.assertEqual(bench.volume_pct, -20.0)
        self.assertEqual(bench.garde_fou_applique, "deload")

    def test_deload_avec_exercice_deja_a_moins_20_conserve_moins_20(self):
        # Régression individuelle plus sévère que le deload : le min() la conserve, elle
        # n'est jamais "remontée" au niveau du deload.
        seance = _decision_seance(deload_actif=True, charge_pct=-15.0, volume_global_pct=-20.0)
        d = composer(seance, _decision_exercice(1, -20.0, "D"), exercice_id=1)
        self.assertEqual(d.charge_pct, -20.0)


class TestCas4TousMauvais(unittest.TestCase):
    def test_chacun_conserve_sa_decision_en_seance_normale(self):
        seance = _decision_seance()
        bench = composer(seance, _decision_exercice(1, -8.0, "D"), exercice_id=1)
        rowing = composer(seance, _decision_exercice(2, -8.0, "D"), exercice_id=2)
        curl = composer(seance, _decision_exercice(3, -8.0, "D"), exercice_id=3)
        self.assertEqual([bench.charge_pct, rowing.charge_pct, curl.charge_pct], [-8.0, -8.0, -8.0])

    def test_puis_deload_si_le_contexte_global_le_declenche(self):
        seance = _decision_seance(deload_actif=True, charge_pct=-15.0, volume_global_pct=-20.0)
        bench = composer(seance, _decision_exercice(1, -8.0, "D"), exercice_id=1)
        rowing = composer(seance, _decision_exercice(2, -8.0, "D"), exercice_id=2)
        curl = composer(seance, _decision_exercice(3, -8.0, "D"), exercice_id=3)
        # min(-8, -15) = -15 : le deload (plus sévère ici) l'emporte pour les trois.
        self.assertEqual([bench.charge_pct, rowing.charge_pct, curl.charge_pct], [-15.0, -15.0, -15.0])


class TestCas5UnSeulMauvais(unittest.TestCase):
    def test_curl_seul_regresse(self):
        seance = _decision_seance()
        bench = composer(seance, _decision_exercice(1, 5.0, "A"), exercice_id=1)
        rowing = composer(seance, _decision_exercice(2, 5.0, "A"), exercice_id=2)
        curl = composer(seance, _decision_exercice(3, -8.0, "D"), exercice_id=3)
        self.assertEqual(bench.charge_pct, 5.0)
        self.assertEqual(rowing.charge_pct, 5.0)
        self.assertEqual(curl.charge_pct, -8.0)


class TestExerciceSansDecision(unittest.TestCase):
    def test_comportement_neutre_explicite(self):
        seance = _decision_seance()
        d = composer(seance, None, exercice_id=42)
        self.assertEqual(d.charge_pct, 0.0)
        self.assertEqual(d.volume_pct, 0.0)
        self.assertEqual(d.confiance, 0.0)
        self.assertEqual(d.source, "defaut")
        self.assertIsNotNone(d.decision_exercice is None)

    def test_exercice_sans_decision_toujours_soumis_au_deload(self):
        seance = _decision_seance(deload_actif=True, charge_pct=-15.0, volume_global_pct=-20.0)
        d = composer(seance, None, exercice_id=42)
        self.assertEqual(d.charge_pct, -15.0)
        self.assertEqual(d.garde_fou_applique, "deload")


class TestAucunEffetDeBord(unittest.TestCase):
    def test_composer_bench_puis_curl_ne_modifie_pas_bench(self):
        seance = _decision_seance()
        decision_bench = _decision_exercice(1, 5.0, "A")
        bench_avant = composer(seance, decision_bench, exercice_id=1)
        composer(seance, _decision_exercice(3, -8.0, "D"), exercice_id=3)  # appel intermédiaire
        bench_apres = composer(seance, decision_bench, exercice_id=1)

        self.assertEqual(bench_avant.charge_pct, bench_apres.charge_pct)
        self.assertEqual(decision_bench.charge_pct, 5.0)  # l'objet d'entrée n'a pas été muté

    def test_meme_decision_seance_reutilisee_sans_mutation(self):
        seance = _decision_seance(deload_actif=True, charge_pct=-15.0)
        composer(seance, _decision_exercice(1, 5.0, "A"), exercice_id=1)
        self.assertEqual(seance.charge_pct, -15.0)  # inchangé après un appel


class TestChargeCibleEtSeriesCible(unittest.TestCase):
    def test_charge_cible_calculee_depuis_la_reference(self):
        seance = _decision_seance()
        d = composer(seance, _decision_exercice(1, 5.0, "A"), exercice_id=1, charge_reference_kg=40.0, series_cible=3)
        self.assertAlmostEqual(d.charge_cible_kg, 42.0)
        self.assertEqual(d.series_cible, 3)

    def test_sans_reference_charge_cible_none(self):
        seance = _decision_seance()
        d = composer(seance, _decision_exercice(1, 5.0, "A"), exercice_id=1)
        self.assertIsNone(d.charge_cible_kg)


if __name__ == "__main__":
    unittest.main()
