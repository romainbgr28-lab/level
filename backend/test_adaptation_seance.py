"""Tests du moteur d'adaptation de séance (adaptation_seance.py).

Module pur : ces tests tournent sans base, sans FastAPI et sans dépendance tierce.

Ce qu'ils protègent, côté produit : quand l'utilisateur dit « je n'ai que 25 minutes »,
« je suis rincé » ou « je suis chez moi », LEVEL doit produire une séance réellement plus
courte / plus légère / réalisable, en gardant le travail prioritaire — et ne jamais
transformer la contrainte en séance arbitraire.

Lancer avec : python3 -m unittest test_adaptation_seance -v (depuis backend/)
"""

import unittest

import adaptation_seance
import duree_seance


def _items(n=4, series=4):
    """n exercices identiques, `series` séries chacun, dans l'ordre de priorité de la séance."""
    return [
        {
            "exercice_id": i,
            "series": series,
            "repetitions": "8",
            "charge_indicative": "24 kg",
            "notes": f"note {i}",
        }
        for i in range(1, n + 1)
    ]


def _meta(n=4, type_exercice="force"):
    return {
        i: {"id": i, "nom": f"Exercice {i}", "type": type_exercice, "materiel_requis_liste": []}
        for i in range(1, n + 1)
    }


class TestAdaptationDuree(unittest.TestCase):
    def test_reduit_la_duree_sous_la_contrainte(self):
        items, meta = _items(), _meta()
        avant = adaptation_seance.duree_estimee_min(items, meta)
        self.assertGreater(avant, 25)

        resultat = adaptation_seance.adapter_pour_duree(items, meta, 25)

        self.assertLessEqual(resultat["duree_apres_min"], 25)
        self.assertLess(resultat["duree_apres_min"], resultat["duree_avant_min"])
        self.assertTrue(resultat["changements"])

    def test_coupe_le_volume_avant_les_exercices(self):
        """On raccourcit d'abord en retirant des séries : un exercice n'est retiré que si
        réduire le volume ne suffit pas. Sinon une contrainte légère ferait disparaître du
        travail prioritaire sans raison."""
        items, meta = _items(n=3, series=5), _meta(n=3)
        cible = adaptation_seance.duree_estimee_min(items, meta) - 6

        resultat = adaptation_seance.adapter_pour_duree(items, meta, cible)

        self.assertEqual(resultat["exercices_retires"], [])
        self.assertEqual(len(resultat["exercices"]), 3)
        self.assertGreater(resultat["series_reduites"], 0)

    def test_retire_les_exercices_les_moins_prioritaires_en_gardant_le_dernier(self):
        """Quand il faut retirer des exercices, le premier (travail principal) et le dernier
        (gainage/prévention de fin de séance) sont préservés — même convention que le
        calibrage à la génération (duree_seance.calibrer_exercices)."""
        items, meta = _items(n=5), _meta(n=5)

        resultat = adaptation_seance.adapter_pour_duree(items, meta, 15)

        ids_restants = [e["exercice_id"] for e in resultat["exercices"]]
        self.assertIn(1, ids_restants, "le travail principal doit être conservé")
        self.assertIn(5, ids_restants, "le gainage de fin de séance est protégé")
        self.assertTrue(resultat["exercices_retires"])

    def test_ne_descend_jamais_sous_le_minimum_de_series(self):
        items, meta = _items(n=2), _meta(n=2)

        resultat = adaptation_seance.adapter_pour_duree(items, meta, 1)

        for exercice in resultat["exercices"]:
            self.assertGreaterEqual(exercice["series"], duree_seance.SERIES_MIN)

    def test_conserve_charges_reps_et_notes(self):
        """Adapter la durée ne réécrit jamais la charge ni les répétitions prévues : réduire
        le volume du jour n'est pas une décision de progression (celle-là appartient à
        adaptation_exercice)."""
        items, meta = _items(), _meta()

        resultat = adaptation_seance.adapter_pour_duree(items, meta, 25)

        for exercice in resultat["exercices"]:
            self.assertEqual(exercice["charge_indicative"], "24 kg")
            self.assertEqual(exercice["repetitions"], "8")
            self.assertEqual(exercice["notes"], f"note {exercice['exercice_id']}")

    def test_seance_qui_tient_deja_est_inchangee(self):
        """Il reste du temps : on n'ajoute pas du volume pour « remplir ». On ne fait que réduire."""
        items, meta = _items(n=2, series=2), _meta(n=2)

        resultat = adaptation_seance.adapter_pour_duree(items, meta, 120)

        self.assertEqual(resultat["exercices"], items)
        self.assertEqual(resultat["series_reduites"], 0)
        self.assertEqual(resultat["exercices_retires"], [])

    def test_seance_vide(self):
        resultat = adaptation_seance.adapter_pour_duree([], {}, 25)
        self.assertEqual(resultat["exercices"], [])


class TestAdaptationFatigue(unittest.TestCase):
    def test_reduit_le_volume_sans_toucher_aux_charges(self):
        items, meta = _items(), _meta()

        resultat = adaptation_seance.adapter_pour_fatigue(items, meta)

        self.assertEqual(resultat["series_reduites"], 4)  # une série par exercice
        for exercice in resultat["exercices"]:
            self.assertEqual(exercice["series"], 3)
            self.assertEqual(exercice["charge_indicative"], "24 kg")

    def test_ne_vide_pas_la_seance(self):
        items, meta = _items(series=duree_seance.SERIES_MIN), _meta()

        resultat = adaptation_seance.adapter_pour_fatigue(items, meta)

        self.assertEqual(resultat["series_reduites"], 0)
        self.assertEqual(len(resultat["exercices"]), 4)
        for exercice in resultat["exercices"]:
            self.assertEqual(exercice["series"], duree_seance.SERIES_MIN)


class TestAdaptationMateriel(unittest.TestCase):
    def test_detecte_les_exercices_impossibles_avec_le_materiel_du_jour(self):
        items = _items(n=3)
        meta = {
            1: {"id": 1, "nom": "Squat barre", "type": "force", "materiel_requis_liste": ["barre"]},
            2: {"id": 2, "nom": "Développé haltères", "type": "force", "materiel_requis_liste": ["halteres"]},
            3: {"id": 3, "nom": "Pompes", "type": "force", "materiel_requis_liste": []},
        }

        incompatibles = adaptation_seance.exercices_incompatibles_materiel(items, meta, "Haltères")

        self.assertEqual(incompatibles, [1], "seul l'exercice à la barre devient impossible")

    def test_salle_complete_permet_tout(self):
        items = _items(n=2)
        meta = {
            1: {"id": 1, "nom": "Squat barre", "type": "force", "materiel_requis_liste": ["barre"]},
            2: {"id": 2, "nom": "Tirage machine", "type": "force", "materiel_requis_liste": ["machine"]},
        }

        self.assertEqual(adaptation_seance.exercices_incompatibles_materiel(items, meta, "Salle complète"), [])

    def test_sans_materiel_seuls_les_exercices_au_poids_du_corps_restent(self):
        items = _items(n=2)
        meta = {
            1: {"id": 1, "nom": "Squat barre", "type": "force", "materiel_requis_liste": ["barre"]},
            2: {"id": 2, "nom": "Pompes", "type": "force", "materiel_requis_liste": []},
        }

        self.assertEqual(adaptation_seance.exercices_incompatibles_materiel(items, meta, "Aucun"), [1])


if __name__ == "__main__":
    unittest.main()
