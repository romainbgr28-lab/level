"""Tests d'intégration — Étape 6 : branchement réel du Moteur d'Adaptation v2 dans
/api/seance/generer.

Contrairement aux tests unitaires existants (test_moteur_decision_par_exercice.py,
test_prompt_par_exercice.py) qui appellent directement moteur_decision.construire_decision()
avec un `exercices_seance` construit à la main, ce fichier prouve le chemin RÉEL emprunté par
l'endpoint : generer_seance() construit lui-même `exercices_seance` à partir du plan calibré et
de l'historique persisté en base, l'utilise pour peupler decision.par_exercice, l'injecte dans le
prompt Mistral, s'en sert pour calculer charges_cibles, et le persiste dans
Seance.decision_adaptation.

Nécessite les dépendances du projet (sqlalchemy, fastapi) — voir requirements.txt. Si elles ne
sont pas installées dans l'environnement d'exécution, ce fichier échoue à l'import
(ModuleNotFoundError), comme les autres tests d'intégration existants du dépôt
(test_historique.py, test_garde_fou_charge.py, test_etape6.py, test_logging_serie.py,
test_adaptation_reps.py) : ce n'est pas une régression introduite ici, c'est une limitation de
l'environnement de test, jamais contournée artificiellement.

Lancer avec : python3 -m unittest test_integration_v2_branchement -v (depuis backend/)
"""

import unittest
from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

import models
import main as main_module


def _setup_db_memoire():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.Base.metadata.create_all(bind=engine)
    return engine, TestSessionLocal


def _reponse_mistral_factice(prompt, system_prompt=None):
    """Remplace mistral_client.appeler_mistral_json : renvoie une séance minimale valide,
    reprenant les exercice_id de la bibliothèque de test (1 = bon exercice, 2 = mauvais
    exercice), avec une charge_indicative volontairement identique et hors de toute cible
    individuelle -- c'est justement ce que le garde-fou (_corriger_charges_hors_tolerance) doit
    corriger différemment pour chacun si les cibles sont bien individualisées."""
    return {
        "nom_seance": "Séance test V2",
        "duree_min": 45,
        "explication": "généré par le test",
        "exercices": [
            {"exercice_id": 1, "series": 3, "repetitions": "8-10", "charge_indicative": "999 kg"},
            {"exercice_id": 2, "series": 3, "repetitions": "8-10", "charge_indicative": "999 kg"},
        ],
    }


class TestBranchementV2GenererSeance(unittest.TestCase):
    """Exercice 1 : reps atteintes + RPE bas -> +5% (cas A). Exercice 2 : reps insuffisantes +
    RPE élevé -> -8% (cas D). Les deux partagent la même charge de référence réelle (50kg) pour
    isoler strictement la différence sur le pourcentage d'ajustement individuel."""

    def setUp(self):
        self.engine, self.TestSessionLocal = _setup_db_memoire()

        def override_get_db():
            db = self.TestSessionLocal()
            try:
                yield db
            finally:
                db.close()

        main_module.app.dependency_overrides[main_module.get_db] = override_get_db
        main_module.app.dependency_overrides[main_module.get_current_date] = lambda: date(2026, 8, 28)
        self.client = TestClient(main_module.app)

        self._appel_mistral_original = main_module.mistral_client.appeler_mistral_json
        main_module.mistral_client.appeler_mistral_json = _reponse_mistral_factice

        with self.TestSessionLocal() as db:
            db.add(models.ExerciceBibliotheque(
                id=1, nom="Développé couché", groupe_musculaire="pectoraux", type="force",
                charge_recommandee="charge_lourde_progressive",
            ))
            db.add(models.ExerciceBibliotheque(
                id=2, nom="Squat", groupe_musculaire="jambes", type="force",
                charge_recommandee="charge_lourde_progressive",
            ))
            db.add(models.Profil(
                id=1, objectifs=[], poste="Milieu", age=25, taille_cm=180.0, poids_kg=75.0,
                niveau_physique="intermediaire",
                niveaux_qualites_physiques={"force": 3, "explosivite": 3, "vitesse": 3, "endurance": 3},
                calendrier_matchs={}, contraintes_temps="45 min", materiel="salle complète",
                objectifs_v2=[], contexte_sportif={"sport": "football"}, disponibilites={},
            ))

            jour_passe = date(2026, 8, 21)

            # Historique réel de charge (source de _derniere_charge_reelle, même mécanisme que
            # l'ancien scalaire) : 50kg pour les deux exercices, séance déjà terminée.
            db.add(models.Seance(id=1, date=jour_passe, nom="Séance passée", exercices=[]))
            db.add(models.SerieLoggee(
                seance_id=1, exercice_id=1, numero_serie=1, poids_kg=50.0, repetitions=10,
                reps_prevues=10, charge_prevue_kg=50.0, rpe_approx=4, coche=1,
            ))
            db.add(models.SerieLoggee(
                seance_id=1, exercice_id=2, numero_serie=1, poids_kg=50.0, repetitions=6,
                reps_prevues=10, charge_prevue_kg=50.0, rpe_approx=9, coche=1,
            ))

            # Historique structuré (source de adaptation_exercice.construire_historique_exercice
            # via _construire_contexte_historique) : même occurrence, exercice 1 réussi (reps
            # atteintes, RPE bas), exercice 2 raté (reps insuffisantes, RPE élevé).
            db.add(models.HistoriqueSeance(
                date=jour_passe, phase_calendaire="phase_normale", type_seance="force",
                exercices_prevus=[], rpe=6, pourcentage_complete=100.0,
                etat_declare_avant={},
                exercices_realises=[
                    {
                        "exercice_id": 1, "nom": "Développé couché", "historique_exercice_ids": [],
                        "series": [{
                            "numero_serie": 1, "poids_kg": 50.0, "repetitions": 10,
                            "reps_prevues": 10, "charge_prevue_kg": 50.0, "rpe_approx": 4,
                        }],
                    },
                    {
                        "exercice_id": 2, "nom": "Squat", "historique_exercice_ids": [],
                        "series": [{
                            "numero_serie": 1, "poids_kg": 50.0, "repetitions": 6,
                            "reps_prevues": 10, "charge_prevue_kg": 50.0, "rpe_approx": 9,
                        }],
                    },
                ],
            ))
            db.commit()

    def tearDown(self):
        main_module.app.dependency_overrides.clear()
        main_module.mistral_client.appeler_mistral_json = self._appel_mistral_original

    def _generer(self):
        payload = {
            "sommeil": "bien", "motivation": "bien", "temps_dispo": "45 min",
            "envie_texte": "", "entrainement_club_semaine": "non",
        }
        return self.client.post("/api/seance/generer", json=payload)

    def test_exercices_seance_transmis_et_par_exercice_rempli(self):
        """Question 1 et 3 de l'audit final : exercices_seance est réellement transmis, et
        decision.par_exercice est réellement non vide en sortie de generer_seance -- vérifié
        indirectement via la persistance (seule fenêtre disponible depuis l'API publique sur
        l'objet DecisionCoaching interne)."""
        reponse = self._generer()
        self.assertEqual(reponse.status_code, 200)
        seance_id = reponse.json()["id"]

        with self.TestSessionLocal() as db:
            seance = db.get(models.Seance, seance_id)
        par_exercice = seance.decision_adaptation.get("par_exercice")
        self.assertTrue(par_exercice, "par_exercice est vide : le branchement exercices_seance a échoué")
        self.assertIn("1", par_exercice)
        self.assertIn("2", par_exercice)

    def test_deux_exercices_deux_charge_pct_differents(self):
        """Question 4 de l'audit final : deux exercices reçoivent réellement deux charge_pct
        différents dans la génération réelle (pas seulement en test unitaire isolé)."""
        reponse = self._generer()
        self.assertEqual(reponse.status_code, 200)
        seance_id = reponse.json()["id"]

        with self.TestSessionLocal() as db:
            seance = db.get(models.Seance, seance_id)
        par_exercice = seance.decision_adaptation["par_exercice"]

        self.assertEqual(par_exercice["1"]["charge_pct"], 5.0)  # cas A : reps atteintes, RPE bas
        self.assertEqual(par_exercice["2"]["charge_pct"], -8.0)  # cas D : reps ratées, RPE haut
        self.assertNotEqual(par_exercice["1"]["charge_pct"], par_exercice["2"]["charge_pct"])

    def test_prompt_mistral_recoit_les_charges_cibles_individuelles(self):
        """Question 5 de l'audit final : le prompt envoyé à Mistral contient réellement le bloc
        de charges cibles par exercice, calculé AVANT l'appel Mistral (jamais après)."""
        prompts_captures = []
        appel_original = main_module.mistral_client.appeler_mistral_json

        def _capture(prompt, system_prompt=None):
            prompts_captures.append(prompt)
            return _reponse_mistral_factice(prompt, system_prompt)

        main_module.mistral_client.appeler_mistral_json = _capture
        try:
            reponse = self._generer()
        finally:
            main_module.mistral_client.appeler_mistral_json = appel_original

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(len(prompts_captures), 1)
        prompt = prompts_captures[0]
        self.assertIn("CHARGES CIBLES PAR EXERCICE", prompt)
        self.assertIn("Développé couché (id 1)", prompt)
        self.assertIn("Squat (id 2)", prompt)
        self.assertIn("ajustement : +5%", prompt)
        self.assertIn("ajustement : -8%", prompt)

    def test_charges_finales_individualisees_apres_correction_garde_fou(self):
        """Question 6 de l'audit final : la charge finale (après correction garde-fou 7.5%/2.5kg)
        reflète réellement decision.par_exercice, pas le scalaire global ajustement_charge_pct
        (qui serait identique pour les deux exercices)."""
        reponse = self._generer()
        self.assertEqual(reponse.status_code, 200)
        exercices = reponse.json()["exercices"]
        charge_ex1 = next(e for e in exercices if e["exercice_id"] == 1)["charge_indicative"]
        charge_ex2 = next(e for e in exercices if e["exercice_id"] == 2)["charge_indicative"]

        # Mistral a renvoyé "999 kg" pour les deux (volontairement absurde et identique) : si la
        # correction utilisait encore le scalaire global ajustement_charge_pct (à ce jour 0.0 par
        # défaut sans garde-fou séance déclenché), les deux charges corrigées seraient identiques
        # (50 kg). Avec le moteur v2 branché, elles doivent diverger (52.5 vs 46 -> arrondi 2.5kg).
        self.assertNotEqual(charge_ex1, charge_ex2)
        self.assertEqual(charge_ex1, "52.5 kg")  # 50 * 1.05 = 52.5 (déjà multiple de 2.5)
        self.assertEqual(charge_ex2, "45 kg")  # 50 * 0.92 = 46.0 -> arrondi 2.5kg -> 45.0

    def test_persistance_contient_le_contrat_complet_par_exercice(self):
        """Question 7 de l'audit final : decision_adaptation["par_exercice"] est bien persisté,
        avec le contrat complet attendu (charge_pct, volume_pct, charge_cible_kg, series_cible,
        raison, confiance, source, garde_fou_applique, decision_exercice) -- pas seulement en
        mémoire pendant la génération."""
        reponse = self._generer()
        seance_id = reponse.json()["id"]

        with self.TestSessionLocal() as db:
            seance = db.get(models.Seance, seance_id)

        # Champs historiques toujours présents (aucune régression du contrat existant).
        for cle in ("ajustement_charge_pct", "ajustement_volume_pct", "charges_cibles", "raisons"):
            self.assertIn(cle, seance.decision_adaptation)

        item = seance.decision_adaptation["par_exercice"]["1"]
        for cle in (
            "exercice_id", "charge_pct", "volume_pct", "charge_cible_kg", "series_cible",
            "raison", "confiance", "source", "garde_fou_applique", "decision_exercice",
        ):
            self.assertIn(cle, item)


if __name__ == "__main__":
    unittest.main()
