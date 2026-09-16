"""Tests de l'annulation d'un match (calendrier_matchs.annulations).

Modules purs (calendrier.py, regles_seance.py) : tournent sans base ni dépendance tierce.

Ce qu'ils protègent, côté produit : « mon match est finalement vendredi au lieu de samedi ».
Avant `annulations`, ajouter le vendredi laissait le samedi habituel actif — l'utilisateur se
retrouvait avec deux jours de match dans la semaine, et le moteur protégeait un match qui
n'existait plus. Les deux lectures du calendrier (calendrier.compute_phase pour classer une
séance passée, regles_seance._dates_matchs_proches pour décider du jour) doivent voir
exactement le même calendrier.

Lancer avec : python3 -m unittest test_calendrier_annulations -v (depuis backend/)
"""

import unittest
from datetime import date

import calendrier
import regles_seance

SAMEDI = date(2026, 9, 19)
VENDREDI = date(2026, 9, 18)
MERCREDI = date(2026, 9, 16)


class TestCompatibiliteAscendante(unittest.TestCase):
    """Un calendrier sans `annulations` (tous les profils existants) se comporte comme avant."""

    def test_jour_habituel_toujours_un_match(self):
        calendrier_matchs = {"jour_habituel": "Samedi", "exceptions": []}
        self.assertEqual(calendrier.compute_phase(SAMEDI, calendrier_matchs), "jour_de_match")
        self.assertEqual(calendrier.compute_phase(VENDREDI, calendrier_matchs), "veille_de_match")

    def test_exception_toujours_un_match(self):
        calendrier_matchs = {"jour_habituel": None, "exceptions": [{"date": "2026-09-18"}]}
        self.assertEqual(calendrier.compute_phase(VENDREDI, calendrier_matchs), "jour_de_match")

    def test_dates_proches_inchangees(self):
        prochain, _ = regles_seance._dates_matchs_proches({"jour_habituel": "Samedi"}, MERCREDI)
        self.assertEqual(prochain, SAMEDI)


class TestDeplacementDeMatch(unittest.TestCase):
    def test_match_deplace_du_samedi_au_vendredi(self):
        calendrier_matchs = {
            "jour_habituel": "Samedi",
            "exceptions": [{"date": "2026-09-18", "label": "Match déplacé"}],
            "annulations": ["2026-09-19"],
        }

        self.assertEqual(calendrier.compute_phase(VENDREDI, calendrier_matchs), "jour_de_match")
        self.assertNotEqual(calendrier.compute_phase(SAMEDI, calendrier_matchs), "jour_de_match")

    def test_le_moteur_de_regles_voit_le_meme_calendrier(self):
        calendrier_matchs = {
            "jour_habituel": "Samedi",
            "exceptions": [{"date": "2026-09-18", "label": "Match déplacé"}],
            "annulations": ["2026-09-19"],
        }

        prochain, _ = regles_seance._dates_matchs_proches(calendrier_matchs, MERCREDI)

        self.assertEqual(prochain, VENDREDI, "le prochain match doit être le vendredi, pas le samedi")

    def test_seul_le_samedi_annule_est_concerne(self):
        """Annuler une occurrence ne supprime pas le match habituel des semaines suivantes."""
        calendrier_matchs = {"jour_habituel": "Samedi", "exceptions": [], "annulations": ["2026-09-19"]}
        samedi_suivant = date(2026, 9, 26)

        self.assertNotEqual(calendrier.compute_phase(SAMEDI, calendrier_matchs), "jour_de_match")
        self.assertEqual(calendrier.compute_phase(samedi_suivant, calendrier_matchs), "jour_de_match")

    def test_annulation_prime_sur_une_exception_de_meme_date(self):
        """Ajouter puis retirer un match ponctuel doit bien le retirer, dans les deux lectures."""
        calendrier_matchs = {
            "jour_habituel": None,
            "exceptions": [{"date": "2026-09-18"}],
            "annulations": ["2026-09-18"],
        }

        self.assertNotEqual(calendrier.compute_phase(VENDREDI, calendrier_matchs), "jour_de_match")
        prochain, _ = regles_seance._dates_matchs_proches(calendrier_matchs, MERCREDI)
        self.assertIsNone(prochain)

    def test_annulations_acceptent_des_objets_date(self):
        """Le calendrier vient tantôt d'une colonne JSON (chaînes), tantôt d'un profil validé
        en mémoire (objets date) : les deux formes doivent être comprises."""
        calendrier_matchs = {"jour_habituel": "Samedi", "exceptions": [], "annulations": [SAMEDI]}

        self.assertNotEqual(calendrier.compute_phase(SAMEDI, calendrier_matchs), "jour_de_match")
        prochain, _ = regles_seance._dates_matchs_proches(calendrier_matchs, MERCREDI)
        self.assertNotEqual(prochain, SAMEDI)


if __name__ == "__main__":
    unittest.main()
