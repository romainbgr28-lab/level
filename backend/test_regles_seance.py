"""Tests unitaires du moteur d'adaptation de charge (calculer_ajustement_charge).

Lancer avec : python3 -m unittest backend.test_regles_seance -v
(ou, depuis backend/ : python3 -m unittest test_regles_seance -v)
"""

import unittest
from datetime import date, timedelta

from regles_seance import _signal_reps_derniere_seance, calculer_ajustement_charge

AUJOURDHUI = date(2026, 8, 25)


def _s(jours_avant: int, rpe, pourcentage, exercices_realises=None):
    entry = {
        "date": AUJOURDHUI - timedelta(days=jours_avant),
        "rpe": rpe,
        "pourcentage_complete": pourcentage,
    }
    if exercices_realises is not None:
        entry["exercices_realises"] = exercices_realises
    return entry


def _exo(exercice_id, series_realisees, reps_prevues, nom=None):
    """Construit un exercice réalisé façon HistoriqueSeance.exercices_realises :
    `series_realisees` est la liste des répétitions réellement faites par série,
    `reps_prevues` la cible unique appliquée à chaque série (cas courant : même
    cible pour toutes les séries d'un exercice, cf. Seance.exercices.repetitions)."""
    return {
        "exercice_id": exercice_id,
        "nom": nom,
        "series": [
            {"numero_serie": i + 1, "repetitions": reps, "reps_prevues": reps_prevues}
            for i, reps in enumerate(series_realisees)
        ],
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


class TestSignalRepsDerniereSeance(unittest.TestCase):
    """Tests unitaires du signal reps prévues vs réalisées (fermeture de boucle demandée :
    les répétitions réellement réalisées doivent participer à l'adaptation)."""

    # 1. reps réalisées = reps prévues -> conforme, aucun signal de réduction.
    def test_reps_conformes(self):
        exos = [_exo(1, [10, 10, 10], 10, nom="Développé couché")]
        signal = _signal_reps_derniere_seance({"exercices_realises": exos})
        self.assertEqual(signal["categorie"], "conforme_ou_superieur")
        self.assertAlmostEqual(signal["ratio"], 1.0)

    # 2. reps légèrement inférieures -> catégorie B.
    def test_reps_legerement_inferieures(self):
        exos = [_exo(1, [9, 8, 9], 10, nom="Développé couché")]
        signal = _signal_reps_derniere_seance({"exercices_realises": exos})
        self.assertEqual(signal["categorie"], "legerement_inferieur")

    # 3. reps nettement inférieures (exemple de la mission : 7/6/6 au lieu de 10/10/10) -> catégorie C.
    def test_reps_nettement_inferieures(self):
        exos = [_exo(1, [7, 6, 6], 10, nom="Développé couché")]
        signal = _signal_reps_derniere_seance({"exercices_realises": exos})
        self.assertEqual(signal["categorie"], "nettement_inferieur")
        self.assertEqual(signal["exercice_id"], 1)

    # 6. Données incomplètes (pas de reps_prevues persistée, ex. série ancienne) -> pas de signal.
    def test_donnees_incompletes_aucun_signal(self):
        exos = [{"exercice_id": 1, "nom": "Développé couché", "series": [{"numero_serie": 1, "repetitions": 8, "reps_prevues": None}]}]
        self.assertIsNone(_signal_reps_derniere_seance({"exercices_realises": exos}))
        self.assertIsNone(_signal_reps_derniere_seance({}))
        self.assertIsNone(_signal_reps_derniere_seance({"exercices_realises": []}))

    # 7. Plusieurs exercices : le pire (ratio le plus faible) détermine le signal de séance,
    # en conservant son identité (lien exercice -> cible -> réalisation).
    def test_plusieurs_exercices_pire_determine_signal(self):
        exos = [
            _exo(1, [10, 10, 10], 10, nom="Développé couché"),  # conforme
            _exo(2, [5, 4, 4], 10, nom="Rowing"),  # nettement inférieur
        ]
        signal = _signal_reps_derniere_seance({"exercices_realises": exos})
        self.assertEqual(signal["categorie"], "nettement_inferieur")
        self.assertEqual(signal["exercice_id"], 2)
        self.assertEqual(signal["nom"], "Rowing")


class TestCalculerAjustementChargeAvecReps(unittest.TestCase):
    """Tests d'intégration du signal reps dans la cascade de calculer_ajustement_charge."""

    # 3. Reps nettement inférieures, RPE modéré, complétion haute (toutes les séries validées,
    # mais chacune sous la cible de reps) : c'est précisément le cas que RPE/complétion seuls
    # ne peuvent pas détecter, cf. mission -> réduction de charge.
    def test_reps_nettement_inferieures_declenche_reduction(self):
        exos = [_exo(1, [7, 6, 6], 10, nom="Développé couché")]
        historique = [_s(2, 6, 100, exercices_realises=exos)]
        r = calculer_ajustement_charge(historique, aujourdhui=AUJOURDHUI)
        self.assertLess(r["charge_pct"], 0.0)
        self.assertIn("Développé couché", r["raison"])

    # 2. Reps légèrement inférieures avec RPE/complétion neutres : ni réduction ni progression.
    def test_reps_legerement_inferieures_bloque_maintien(self):
        exos = [_exo(1, [9, 8, 9], 10, nom="Développé couché")]
        historique = [_s(2, 6, 100, exercices_realises=exos)]
        r = calculer_ajustement_charge(historique, aujourdhui=AUJOURDHUI)
        self.assertEqual(r["charge_pct"], 0.0)
        self.assertEqual(r["volume_pct"], 0.0)

    # 1. Reps prévues atteintes exactement + RPE faible sur 3 séances -> signal de progression
    # inchangé (règle 5 existante), le signal reps ne bloque pas la progression légitime.
    def test_reps_conformes_rpe_faible_progression_confirmee(self):
        exos = [_exo(1, [10, 10, 10], 10, nom="Développé couché")]
        historique = [
            _s(2, 5, 95, exercices_realises=exos),
            _s(9, 4, 100, exercices_realises=exos),
            _s(16, 5, 92, exercices_realises=exos),
        ]
        r = calculer_ajustement_charge(historique, aujourdhui=AUJOURDHUI)
        self.assertEqual(r["charge_pct"], 8.0)
        self.assertEqual(r["volume_pct"], 5.0)

    # 4. reps nettement inférieures + RPE élevé : une seule décision (pas de cumul RPE + reps
    # + complétion) -- c'est la règle RPE (priorité plus haute dans la cascade) qui tranche.
    def test_reps_faibles_et_rpe_eleve_pas_de_cumul(self):
        exos = [_exo(1, [7, 6, 6], 10, nom="Développé couché")]
        historique = [_s(2, 9, 60, exercices_realises=exos)]
        r = calculer_ajustement_charge(historique, aujourdhui=AUJOURDHUI)
        # Décision de la règle RPE>=9 (charge -10%, volume -12%), jamais cumulée avec la
        # réduction reps (-8%/-5%) ni la réduction complétion (-5%/-10%).
        self.assertEqual(r["charge_pct"], -10.0)
        self.assertEqual(r["volume_pct"], -12.0)

    # 6. Historique sans donnée reps (comportement d'avant l'ajout, séances anciennes) :
    # résultat inchangé, uniquement piloté par RPE/complétion.
    def test_historique_sans_donnees_reps_comportement_inchange(self):
        historique = [_s(2, 5, 100)]
        r = calculer_ajustement_charge(historique, aujourdhui=AUJOURDHUI)
        self.assertEqual(r["charge_pct"], 0.0)
        self.assertEqual(r["volume_pct"], 0.0)

    # 7. Plusieurs exercices avec performances différentes : le pire pilote la décision de
    # séance, avec traçabilité vers l'exercice concerné.
    def test_plusieurs_exercices_performances_differentes(self):
        exos = [
            _exo(1, [10, 10, 10], 10, nom="Développé couché"),
            _exo(2, [5, 4, 4], 10, nom="Rowing"),
        ]
        historique = [_s(2, 6, 100, exercices_realises=exos)]
        r = calculer_ajustement_charge(historique, aujourdhui=AUJOURDHUI)
        self.assertLess(r["charge_pct"], 0.0)
        self.assertIn("Rowing", r["raison"])
        self.assertNotIn("Développé couché", r["raison"])


if __name__ == "__main__":
    unittest.main()
