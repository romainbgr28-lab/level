"""Tests unitaires du calibrage volume/temps (duree_seance.calibrer_exercices).

Lancer avec : python3 -m unittest backend.test_duree_seance -v
(ou, depuis backend/ : python3 -m unittest test_duree_seance -v)
"""

import unittest
from types import SimpleNamespace

from duree_seance import (
    SERIES_MIN,
    SERIES_PAR_DEFAUT,
    calibrer_exercices,
    series_cible_depuis_ajustement,
)


def _ex(id_, type_="force"):
    return SimpleNamespace(id=id_, type=type_)


class TestSeriesCibleDepuisAjustement(unittest.TestCase):
    def test_ajustement_nul(self):
        self.assertEqual(series_cible_depuis_ajustement(0.0), SERIES_PAR_DEFAUT)

    def test_ajustement_none(self):
        self.assertEqual(series_cible_depuis_ajustement(None), SERIES_PAR_DEFAUT)

    def test_progression(self):
        # +30% de 3 séries -> 3.9 arrondi à 4
        self.assertEqual(series_cible_depuis_ajustement(30.0), 4)

    def test_reduction(self):
        # -30% de 3 séries -> 2.1 arrondi à 2
        self.assertEqual(series_cible_depuis_ajustement(-30.0), 2)

    def test_reduction_forte_plancher_series_min(self):
        # -80% de 3 séries -> 0.6, jamais en dessous de SERIES_MIN
        self.assertEqual(series_cible_depuis_ajustement(-80.0), SERIES_MIN)


class TestCalibrerExercices(unittest.TestCase):
    def test_volume_neutre_comportement_actuel(self):
        candidats = [_ex(1), _ex(2)]
        plan = calibrer_exercices(candidats, temps_dispo_min=None)
        self.assertTrue(all(p["series"] == SERIES_PAR_DEFAUT for p in plan))

    def test_progression_volume_series_augmentees_si_temps_suffisant(self):
        candidats = [_ex(1)]
        plan = calibrer_exercices(candidats, temps_dispo_min=60, series_cible=4)
        self.assertEqual(plan[0]["series"], 4)

    def test_reduction_volume_series_reduites(self):
        candidats = [_ex(1), _ex(2)]
        plan = calibrer_exercices(candidats, temps_dispo_min=None, series_cible=2)
        self.assertTrue(all(p["series"] == 2 for p in plan))

    def test_volume_augmente_mais_temps_insuffisant_reduit_par_calibrage_temps(self):
        candidats = [_ex(1), _ex(2), _ex(3)]
        # series_cible=5 mais temps très court : le calibrage temps doit ramener les
        # séries en dessous de la cible, jusqu'à SERIES_MIN si besoin.
        plan = calibrer_exercices(candidats, temps_dispo_min=15, series_cible=5)
        self.assertTrue(all(p["series"] <= 5 for p in plan))
        self.assertTrue(any(p["series"] < 5 for p in plan))
        self.assertTrue(all(p["series"] >= SERIES_MIN for p in plan))

    def test_fallback_sans_regression_liste_vide(self):
        plan = calibrer_exercices([], temps_dispo_min=45, series_cible=4)
        self.assertEqual(plan, [])


if __name__ == "__main__":
    unittest.main()
