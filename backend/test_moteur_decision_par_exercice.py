"""Tests unitaires — Moteur d'Adaptation LEVEL v2, Étape 4 : intégration dans l'orchestrateur
(moteur_decision.construire_decision -> DecisionCoaching.par_exercice).

Lancer avec : python3 -m unittest test_moteur_decision_par_exercice -v (depuis backend/)
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


def _occurrence(jours_avant, exercice_id=1, reps_prevues=10, repetitions=10, rpe=6.0, poids_kg=50.0, charge_prevue_kg=50.0):
    return {
        "exercice_id": exercice_id,
        "nom": "Développé couché",
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


def _seance(jours_avant, type_seance="force", exercices_realises=None, today=None):
    today = today or date.today()
    return {
        "date": today - timedelta(days=jours_avant),
        "rpe": 6,
        "pourcentage_complete": 100,
        "type_seance": type_seance,
        "exercices_realises": exercices_realises or [],
    }


def _historique_avec_seances(seances, type_seance="force"):
    return {
        "par_type": {type_seance: seances[:3]},
        "recent": seances[:3],
        "zones_sensibles_recentes": [],
    }


class TestParExerciceRetrocompatibilite(unittest.TestCase):
    """Rétrocompatibilité totale : construire_decision sans exercices_seance (aucun appelant
    existant ne le passe) doit continuer à produire exactement le même comportement qu'avant,
    par_exercice restant simplement vide."""

    def test_ancien_format_sans_exercices_seance(self):
        decision = moteur_decision.construire_decision(
            PROFIL_MINIMAL, _historique_vide(), ETAT_DU_JOUR_MINIMAL, aujourdhui=date.today()
        )
        self.assertEqual(decision.par_exercice, {})
        d = decision.to_dict()
        self.assertIn("par_exercice", d)
        self.assertEqual(d["par_exercice"], {})
        # tous les champs existants doivent rester présents et inchangés dans leur contrat
        for cle in (
            "objectifs_prioritaires", "objectif_principal", "objectif_secondaire",
            "qualites_prioritaires", "type_seance_recommande", "focus_principal",
            "niveau_effectif", "contraintes", "ajustements", "raisons", "confiance_decision",
        ):
            self.assertIn(cle, d)

    def test_exercices_seance_none_explicite(self):
        decision = moteur_decision.construire_decision(
            PROFIL_MINIMAL, _historique_vide(), ETAT_DU_JOUR_MINIMAL, aujourdhui=date.today(),
            exercices_seance=None,
        )
        self.assertEqual(decision.par_exercice, {})

    def test_exercices_seance_liste_vide(self):
        decision = moteur_decision.construire_decision(
            PROFIL_MINIMAL, _historique_vide(), ETAT_DU_JOUR_MINIMAL, aujourdhui=date.today(),
            exercices_seance=[],
        )
        self.assertEqual(decision.par_exercice, {})


class TestParExerciceHistoriqueVideOuReel(unittest.TestCase):
    def test_historique_vide_jamais_realise(self):
        decision = moteur_decision.construire_decision(
            PROFIL_MINIMAL, _historique_vide(), ETAT_DU_JOUR_MINIMAL, aujourdhui=date.today(),
            exercices_seance=[{"exercice_id": 1}],
        )
        self.assertIn(1, decision.par_exercice)
        item = decision.par_exercice[1]
        self.assertEqual(item["decision_exercice"]["regle_gagnante"], "jamais_realise")
        self.assertEqual(item["charge_pct"], 0.0)
        self.assertIsNone(item["garde_fou_applique"])

    def test_historique_reel_progression(self):
        today = date.today()
        # Cas A : reps atteintes (10/10), charge stable, RPE bas (4 <= 5) -> progression standard.
        seances = [_seance(3, exercices_realises=[_occurrence(3, rpe=4.0)], today=today)]
        historique = _historique_avec_seances(seances)
        decision = moteur_decision.construire_decision(
            PROFIL_MINIMAL, historique, ETAT_DU_JOUR_MINIMAL, aujourdhui=today,
            exercices_seance=[{"exercice_id": 1, "charge_reference_kg": 50.0, "series_cible": 3}],
        )
        item = decision.par_exercice[1]
        self.assertEqual(item["decision_exercice"]["regle_gagnante"], "A")
        self.assertEqual(item["charge_pct"], 5.0)
        self.assertAlmostEqual(item["charge_cible_kg"], 52.5)
        self.assertEqual(item["series_cible"], 3)


class TestParExerciceRemplacement(unittest.TestCase):
    def test_exercice_remplace_via_historique_exercice_ids(self):
        today = date.today()
        # L'exercice 2 (nouveau) remplace l'exercice 1 (ancien) : l'historique de l'ancien doit
        # être retrouvé via historique_exercice_ids, avec exercice_id=2 dans la sortie.
        seances = [_seance(3, exercices_realises=[_occurrence(3, exercice_id=1, rpe=4.0)], today=today)]
        historique = _historique_avec_seances(seances)
        decision = moteur_decision.construire_decision(
            PROFIL_MINIMAL, historique, ETAT_DU_JOUR_MINIMAL, aujourdhui=today,
            exercices_seance=[{"exercice_id": 2, "historique_exercice_ids": [1]}],
        )
        self.assertIn(2, decision.par_exercice)
        self.assertNotIn(1, decision.par_exercice)
        self.assertEqual(decision.par_exercice[2]["decision_exercice"]["regle_gagnante"], "A")


class TestParExerciceBonEtMauvais(unittest.TestCase):
    def test_un_exercice_bon_un_mauvais(self):
        today = date.today()
        seances = [
            _seance(
                3,
                exercices_realises=[
                    _occurrence(3, exercice_id=1, rpe=4.0),  # bon : reps atteintes, RPE bas
                    _occurrence(3, exercice_id=2, repetitions=6, rpe=9.0),  # mauvais : reps ratées, RPE haut
                ],
                today=today,
            )
        ]
        historique = _historique_avec_seances(seances)
        decision = moteur_decision.construire_decision(
            PROFIL_MINIMAL, historique, ETAT_DU_JOUR_MINIMAL, aujourdhui=today,
            exercices_seance=[{"exercice_id": 1}, {"exercice_id": 2}],
        )
        self.assertEqual(decision.par_exercice[1]["decision_exercice"]["regle_gagnante"], "A")
        self.assertEqual(decision.par_exercice[1]["charge_pct"], 5.0)
        self.assertEqual(decision.par_exercice[2]["decision_exercice"]["regle_gagnante"], "D")
        self.assertEqual(decision.par_exercice[2]["charge_pct"], -8.0)
        # PAS de contamination croisée : le mauvais exercice n'affecte pas le bon.
        self.assertNotEqual(decision.par_exercice[1]["charge_pct"], decision.par_exercice[2]["charge_pct"])


class TestParExerciceDeloadEtFatigue(unittest.TestCase):
    def test_deload_actif_ecrase_progression(self):
        today = date.today()
        # 3 séances consécutives ratées -> appliquer_garde_fous force type_seance_suggere =
        # "décharge" (regles_seance.py), qui doit se traduire par deload_actif=True côté
        # composition, et écraser une progression individuelle (min()).
        historique_recent_rate = [
            {"date": today - timedelta(days=i * 3), "rpe": 9, "pourcentage_complete": 50, "exercices_realises": []}
            for i in range(1, 4)
        ]
        seances_exo = [_seance(3, exercices_realises=[_occurrence(3, rpe=4.0)], today=today)]
        historique = {
            "par_type": {"force": seances_exo},
            "recent": historique_recent_rate,
            "zones_sensibles_recentes": [],
        }
        decision = moteur_decision.construire_decision(
            PROFIL_MINIMAL, historique, ETAT_DU_JOUR_MINIMAL, aujourdhui=today,
            exercices_seance=[{"exercice_id": 1}],
        )
        self.assertEqual(decision.type_seance_recommande, "décharge")
        item = decision.par_exercice[1]
        # Progression individuelle (cas A, +5%) plafonnée par le deload (charge_pct de la
        # décision séance, -30% côté volume mais charge_pct vient d'ajustement_charge_pct=0.0
        # par défaut sur ce chemin -> min(+5, 0.0) = 0.0).
        self.assertLessEqual(item["charge_pct"], 0.0)
        self.assertEqual(item["garde_fou_applique"], "deload")

    def test_fatigue_non_critique_reste_normale(self):
        # Sans signal de décharge, fatigue_globale reste "normale" (limitation Étape 4 : pas
        # d'état "elevee" distinct exposé par regles_seance aujourd'hui) -> pas de plafond
        # fatigue appliqué, la progression individuelle passe intacte.
        today = date.today()
        seances = [_seance(3, exercices_realises=[_occurrence(3, rpe=4.0)], today=today)]
        historique = _historique_avec_seances(seances)
        decision = moteur_decision.construire_decision(
            PROFIL_MINIMAL, historique, ETAT_DU_JOUR_MINIMAL, aujourdhui=today,
            exercices_seance=[{"exercice_id": 1}],
        )
        item = decision.par_exercice[1]
        self.assertIsNone(item["garde_fou_applique"])
        self.assertEqual(item["charge_pct"], 5.0)


class TestParExerciceDonneesAbsentes(unittest.TestCase):
    def test_absence_de_rpe(self):
        today = date.today()
        occ = _occurrence(3, rpe=None)
        occ["series"][0]["rpe_approx"] = None
        seances = [_seance(3, exercices_realises=[occ], today=today)]
        historique = _historique_avec_seances(seances)
        decision = moteur_decision.construire_decision(
            PROFIL_MINIMAL, historique, ETAT_DU_JOUR_MINIMAL, aujourdhui=today,
            exercices_seance=[{"exercice_id": 1}],
        )
        item = decision.par_exercice[1]
        # Reps atteintes mais RPE absent -> aucune branche de la matrice n'est satisfaite
        # (rpe_bas/rpe_haut nécessitent tous deux rpe non None) -> neutre.
        self.assertEqual(item["decision_exercice"]["regle_gagnante"], "neutre")
        self.assertEqual(item["charge_pct"], 0.0)

    def test_absence_de_reps_prevues(self):
        today = date.today()
        occ = _occurrence(3, reps_prevues=None)
        occ["series"][0]["reps_prevues"] = None
        seances = [_seance(3, exercices_realises=[occ], today=today)]
        historique = _historique_avec_seances(seances)
        decision = moteur_decision.construire_decision(
            PROFIL_MINIMAL, historique, ETAT_DU_JOUR_MINIMAL, aujourdhui=today,
            exercices_seance=[{"exercice_id": 1}],
        )
        item = decision.par_exercice[1]
        self.assertEqual(item["decision_exercice"]["regle_gagnante"], "neutre")
        self.assertEqual(item["confiance"], 0.4)  # signaux incomplets -> confiance basse


class TestParExerciceStructureEtChampsExistants(unittest.TestCase):
    def test_presence_par_exercice_sans_casser_champs_existants(self):
        today = date.today()
        seances = [_seance(3, exercices_realises=[_occurrence(3, rpe=4.0)], today=today)]
        historique = _historique_avec_seances(seances)
        decision = moteur_decision.construire_decision(
            PROFIL_MINIMAL, historique, ETAT_DU_JOUR_MINIMAL, aujourdhui=today,
            exercices_seance=[{"exercice_id": 1, "charge_reference_kg": 50.0, "series_cible": 4}],
        )
        d = decision.to_dict()
        self.assertIsInstance(d["par_exercice"], dict)
        self.assertIn(1, d["par_exercice"])
        item = d["par_exercice"][1]
        for cle in (
            "exercice_id", "charge_pct", "volume_pct", "charge_cible_kg", "series_cible",
            "raison", "confiance", "source", "garde_fou_applique", "decision_exercice",
        ):
            self.assertIn(cle, item)
        # champs existants toujours présents et cohérents avec le comportement d'avant l'Étape 4
        self.assertEqual(d["type_seance_recommande"], decision.type_seance_recommande)
        self.assertIsInstance(d["ajustements"], dict)


if __name__ == "__main__":
    unittest.main()
