"""Tests unitaires — bilan.construire_bilan.

Vérifie que chaque chiffre du bilan provient bien des données fournies (aucune métrique
fabriquée), que la fenêtre temporelle est respectée, et que l'absence de données produit un
bilan vide plutôt que du remplissage.

Lancer avec : python3 -m unittest test_bilan -v (depuis backend/)
"""

import unittest
from datetime import date, timedelta

import bilan

AUJOURDHUI = date(2026, 3, 15)  # un dimanche


def _serie(jours_avant, nom, poids=50.0, reps=10, coche=True):
    return {
        "date": AUJOURDHUI - timedelta(days=jours_avant),
        "nom_exercice": nom,
        "poids_kg": poids,
        "repetitions": reps,
        "coche": coche,
    }


def _seance(jours_avant, rpe=7, pourcentage=100.0):
    return {
        "date": AUJOURDHUI - timedelta(days=jours_avant),
        "rpe": rpe,
        "pourcentage_complete": pourcentage,
        "type_seance": "force",
    }


class TestBilanVide(unittest.TestCase):
    def test_aucune_donnee_ne_fabrique_rien(self):
        b = bilan.construire_bilan([], [], AUJOURDHUI)
        self.assertEqual(b["seances_realisees"], 0)
        self.assertEqual(b["volume_kg"], 0.0)
        self.assertIsNone(b["rpe_moyen"])
        self.assertIsNone(b["completion_moyenne"])
        self.assertEqual(b["progressions"], [])
        self.assertEqual(b["stagnations"], [])
        self.assertEqual(len(b["points"]), 1)
        self.assertIn("Aucune séance", b["points"][0])

    def test_periode_couvre_bien_sept_jours_inclusifs(self):
        b = bilan.construire_bilan([], [], AUJOURDHUI)
        self.assertEqual(b["periode_fin"], "2026-03-15")
        self.assertEqual(b["periode_debut"], "2026-03-09")


class TestFenetreTemporelle(unittest.TestCase):
    def test_seance_hors_fenetre_non_comptee(self):
        b = bilan.construire_bilan([_seance(0), _seance(20)], [], AUJOURDHUI)
        self.assertEqual(b["seances_realisees"], 1)

    def test_seance_de_la_semaine_precedente_va_dans_le_comparatif(self):
        b = bilan.construire_bilan([_seance(1), _seance(8)], [], AUJOURDHUI)
        self.assertEqual(b["seances_realisees"], 1)
        self.assertEqual(b["seances_realisees_precedent"], 1)

    def test_borne_basse_incluse(self):
        b = bilan.construire_bilan([_seance(6)], [], AUJOURDHUI)
        self.assertEqual(b["seances_realisees"], 1)

    def test_jours_actifs_dedoublonne_les_seances_du_meme_jour(self):
        b = bilan.construire_bilan([_seance(2), _seance(2), _seance(3)], [], AUJOURDHUI)
        self.assertEqual(b["seances_realisees"], 3)
        self.assertEqual(b["jours_actifs"], 2)


class TestVolume(unittest.TestCase):
    def test_volume_somme_poids_fois_reps_des_series_cochees(self):
        series = [_serie(1, "Bench", 60.0, 10), _serie(2, "Squat", 80.0, 5)]
        b = bilan.construire_bilan([_seance(1)], series, AUJOURDHUI)
        self.assertEqual(b["volume_kg"], 600.0 + 400.0)

    def test_serie_non_cochee_ignoree(self):
        series = [_serie(1, "Bench", 60.0, 10, coche=False)]
        b = bilan.construire_bilan([_seance(1)], series, AUJOURDHUI)
        self.assertEqual(b["volume_kg"], 0.0)

    def test_poids_du_corps_ne_contribue_pas_au_volume_kg(self):
        series = [_serie(1, "Pompes", None, 20)]
        b = bilan.construire_bilan([_seance(1)], series, AUJOURDHUI)
        self.assertEqual(b["volume_kg"], 0.0)

    def test_variation_volume_none_si_pas_de_reference(self):
        b = bilan.construire_bilan([_seance(1)], [_serie(1, "Bench", 60.0, 10)], AUJOURDHUI)
        self.assertIsNone(b["volume_variation_pct"])

    def test_variation_volume_calculee_sur_la_semaine_precedente(self):
        series = [_serie(1, "Bench", 60.0, 10), _serie(8, "Bench", 50.0, 10)]
        b = bilan.construire_bilan([_seance(1), _seance(8)], series, AUJOURDHUI)
        self.assertEqual(b["volume_kg"], 600.0)
        self.assertEqual(b["volume_kg_precedent"], 500.0)
        self.assertEqual(b["volume_variation_pct"], 20.0)


class TestProgressionsEtStagnations(unittest.TestCase):
    def test_progression_detectee_au_dela_du_seuil(self):
        series = [_serie(1, "Bench", 60.0), _serie(8, "Bench", 50.0)]
        b = bilan.construire_bilan([_seance(1), _seance(8)], series, AUJOURDHUI)
        self.assertEqual(len(b["progressions"]), 1)
        self.assertEqual(b["progressions"][0]["exercice"], "Bench")
        self.assertEqual(b["progressions"][0]["variation_pct"], 20.0)
        self.assertEqual(b["stagnations"], [])

    def test_stagnation_quand_charge_identique(self):
        series = [_serie(1, "Bench", 60.0), _serie(8, "Bench", 60.0)]
        b = bilan.construire_bilan([_seance(1), _seance(8)], series, AUJOURDHUI)
        self.assertEqual(b["progressions"], [])
        self.assertEqual(b["stagnations"], [{"exercice": "Bench", "charge_kg": 60.0}])

    def test_exercice_sans_reference_precedente_nest_ni_progression_ni_stagnation(self):
        b = bilan.construire_bilan([_seance(1)], [_serie(1, "Bench", 60.0)], AUJOURDHUI)
        self.assertEqual(b["progressions"], [])
        self.assertEqual(b["stagnations"], [])

    def test_progressions_triees_par_variation_decroissante_et_plafonnees(self):
        series = []
        for i, nom in enumerate(["A", "B", "C", "D"]):
            series.append(_serie(1, nom, 50.0 + i * 10))
            series.append(_serie(8, nom, 40.0))
        b = bilan.construire_bilan([_seance(1), _seance(8)], series, AUJOURDHUI)
        self.assertEqual(len(b["progressions"]), bilan.MAX_EXERCICES_LISTES)
        variations = [p["variation_pct"] for p in b["progressions"]]
        self.assertEqual(variations, sorted(variations, reverse=True))
        self.assertEqual(b["progressions"][0]["exercice"], "D")

    def test_charge_max_retenue_et_non_la_derniere(self):
        series = [_serie(1, "Bench", 70.0), _serie(2, "Bench", 60.0), _serie(8, "Bench", 50.0)]
        b = bilan.construire_bilan([_seance(1), _seance(8)], series, AUJOURDHUI)
        self.assertEqual(b["progressions"][0]["charge_kg"], 70.0)


class TestMoyennes(unittest.TestCase):
    def test_rpe_moyen_ignore_les_seances_sans_rpe(self):
        b = bilan.construire_bilan([_seance(1, rpe=6), _seance(2, rpe=8), _seance(3, rpe=None)], [], AUJOURDHUI)
        self.assertEqual(b["rpe_moyen"], 7.0)

    def test_completion_moyenne(self):
        b = bilan.construire_bilan(
            [_seance(1, pourcentage=100.0), _seance(2, pourcentage=50.0)], [], AUJOURDHUI
        )
        self.assertEqual(b["completion_moyenne"], 75.0)


class TestPoints(unittest.TestCase):
    def test_points_courts_et_bornes(self):
        series = [_serie(1, "Bench", 60.0), _serie(8, "Bench", 50.0)]
        b = bilan.construire_bilan([_seance(1), _seance(2), _seance(8)], series, AUJOURDHUI)
        self.assertGreaterEqual(len(b["points"]), 2)
        self.assertLessEqual(len(b["points"]), 4)

    def test_point_progression_cite_lexercice_reel(self):
        series = [_serie(1, "Squat", 100.0), _serie(8, "Squat", 80.0)]
        b = bilan.construire_bilan([_seance(1), _seance(8)], series, AUJOURDHUI)
        self.assertTrue(any("Squat" in p for p in b["points"]))

    def test_completion_faible_signalee(self):
        b = bilan.construire_bilan([_seance(1, pourcentage=40.0)], [], AUJOURDHUI)
        self.assertTrue(any("non validées" in p for p in b["points"]))


if __name__ == "__main__":
    unittest.main()
