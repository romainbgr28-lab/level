"""Tests unitaires — Moteur d'Adaptation LEVEL v2, Étape 1 : historique par exercice
(adaptation_exercice.construire_historique_exercice). Fonctions pures, sans FastAPI/SQLAlchemy.

Lancer avec : python3 -m unittest test_adaptation_exercice -v (depuis backend/)
"""

import unittest
from datetime import date

from adaptation_exercice import construire_historique_exercice


def _seance(jour: str, exercices_realises=None):
    return {"date": jour, "exercices_realises": exercices_realises}


def _exo(exercice_id, series):
    return {"exercice_id": exercice_id, "series": series}


def _serie(numero=1, poids_kg=20.0, repetitions=10, reps_prevues=10, charge_prevue_kg=20.0, rpe_approx=6):
    return {
        "numero_serie": numero,
        "poids_kg": poids_kg,
        "repetitions": repetitions,
        "reps_prevues": reps_prevues,
        "charge_prevue_kg": charge_prevue_kg,
        "rpe_approx": rpe_approx,
    }


class TestJamaisRealise(unittest.TestCase):
    def test_aucune_seance(self):
        h = construire_historique_exercice([], exercice_id=1)
        self.assertTrue(h.jamais_realise)
        self.assertEqual(h.occurrences, [])
        self.assertEqual(h.nb_occurrences, 0)

    def test_exercice_absent_de_tout_lhistorique(self):
        seances = [_seance("2026-08-20", [_exo(2, [_serie()])])]
        h = construire_historique_exercice(seances, exercice_id=1)
        self.assertTrue(h.jamais_realise)

    def test_seance_sans_exercices_realises(self):
        h = construire_historique_exercice([{"date": "2026-08-20"}], exercice_id=1)
        self.assertTrue(h.jamais_realise)


class TestUneOccurrence(unittest.TestCase):
    def test_une_seule_occurrence(self):
        seances = [_seance("2026-08-20", [_exo(1, [_serie()])])]
        h = construire_historique_exercice(seances, exercice_id=1)
        self.assertFalse(h.jamais_realise)
        self.assertEqual(h.nb_occurrences, 1)
        self.assertEqual(h.occurrences[0].exercice_id, 1)
        self.assertEqual(h.occurrences[0].date, date(2026, 8, 20))


class TestPlusieursOccurrences(unittest.TestCase):
    def test_ordre_plus_recent_dabord(self):
        seances = [
            _seance("2026-08-10", [_exo(1, [_serie(poids_kg=15)])]),
            _seance("2026-08-20", [_exo(1, [_serie(poids_kg=20)])]),
            _seance("2026-08-15", [_exo(1, [_serie(poids_kg=17)])]),
        ]
        h = construire_historique_exercice(seances, exercice_id=1)
        self.assertEqual(h.nb_occurrences, 3)
        self.assertEqual([o.date for o in h.occurrences], [date(2026, 8, 20), date(2026, 8, 15), date(2026, 8, 10)])

    def test_fenetre_limite_le_nombre_retenu(self):
        seances = [_seance(f"2026-08-{10+i:02d}", [_exo(1, [_serie()])]) for i in range(12)]
        h = construire_historique_exercice(seances, exercice_id=1, fenetre=5)
        self.assertEqual(h.nb_occurrences, 5)
        # Les 5 les plus récentes : jours 21 à 17 (10+11=21 en partant de i=0..11).
        self.assertEqual(h.occurrences[0].date, date(2026, 8, 21))


class TestAbsentDeLaDerniereSeance(unittest.TestCase):
    def test_absent_recemment_mais_trouve_plus_loin(self):
        seances = [
            _seance("2026-08-25", [_exo(2, [_serie()])]),  # exercice 1 absent ici
            _seance("2026-08-20", [_exo(1, [_serie()])]),  # dernière vraie occurrence
        ]
        h = construire_historique_exercice(seances, exercice_id=1)
        self.assertFalse(h.jamais_realise)
        self.assertEqual(h.nb_occurrences, 1)
        self.assertEqual(h.occurrences[0].date, date(2026, 8, 20))


class TestSubstitution(unittest.TestCase):
    def test_slot_suivi_via_exercice_ids_lies(self):
        # Exercice courant = 20 (nouveau), mais le slot était l'exercice 10 lors des deux
        # séances précédentes (avant substitution) : exercice_ids_lies permet de les retrouver.
        seances = [
            _seance("2026-08-10", [_exo(10, [_serie(poids_kg=18)])]),
            _seance("2026-08-15", [_exo(10, [_serie(poids_kg=19)])]),
        ]
        h = construire_historique_exercice(seances, exercice_id=20, exercice_ids_lies={10})
        self.assertFalse(h.jamais_realise)
        self.assertEqual(h.nb_occurrences, 2)
        self.assertTrue(all(o.exercice_id == 10 for o in h.occurrences))
        # HistoriqueExercice.exercice_id reste l'exercice COURANT (20), pas l'ancien (spec 5.5).
        self.assertEqual(h.exercice_id, 20)

    def test_sans_exercice_ids_lies_substitution_non_retrouvee(self):
        seances = [_seance("2026-08-10", [_exo(10, [_serie()])])]
        h = construire_historique_exercice(seances, exercice_id=20)
        self.assertTrue(h.jamais_realise)


class TestDonneesPartielles(unittest.TestCase):
    def test_serie_sans_reps_prevues(self):
        serie = _serie(reps_prevues=None)
        seances = [_seance("2026-08-20", [_exo(1, [serie])])]
        h = construire_historique_exercice(seances, exercice_id=1)
        self.assertFalse(h.jamais_realise)
        self.assertIsNone(h.occurrences[0].series[0]["reps_prevues"])

    def test_serie_sans_rpe_approx(self):
        serie = _serie(rpe_approx=None)
        seances = [_seance("2026-08-20", [_exo(1, [serie])])]
        h = construire_historique_exercice(seances, exercice_id=1)
        self.assertFalse(h.jamais_realise)
        self.assertIsNone(h.occurrences[0].series[0]["rpe_approx"])

    def test_exercices_realises_liste_vide(self):
        seances = [_seance("2026-08-20", [])]
        h = construire_historique_exercice(seances, exercice_id=1)
        self.assertTrue(h.jamais_realise)

    def test_series_liste_vide_toujours_une_occurrence(self):
        # item présent mais sans série validée -> occurrence conservée avec series=[] (donnée
        # partielle, jamais une exception ni un rejet silencieux de la séance entière).
        seances = [_seance("2026-08-20", [_exo(1, [])])]
        h = construire_historique_exercice(seances, exercice_id=1)
        self.assertFalse(h.jamais_realise)
        self.assertEqual(h.occurrences[0].series, [])

    def test_ancienne_serie_sans_aucun_champ_v2(self):
        # Séance antérieure à l'ajout de reps_prevues/charge_prevue_kg/rpe_approx.
        serie_ancienne = {"numero_serie": 1, "poids_kg": 20.0, "repetitions": 10}
        seances = [_seance("2026-08-01", [_exo(1, [serie_ancienne])])]
        h = construire_historique_exercice(seances, exercice_id=1)
        self.assertFalse(h.jamais_realise)
        self.assertEqual(h.occurrences[0].series[0].get("reps_prevues"), None)
        self.assertEqual(h.occurrences[0].series[0].get("rpe_approx"), None)


if __name__ == "__main__":
    unittest.main()
