"""Tests de l'Étape 2 (historique visible) : enrichissement des noms d'exercices prévus,
endpoint GET /api/historique_seances, et le graphique de charge rebranché sur SerieLoggee.

Nécessite les dépendances du projet (sqlalchemy, fastapi) — voir requirements.txt.
Lancer avec : python3 -m unittest backend.test_historique -v
(ou, depuis backend/ : python3 -m unittest test_historique -v)
"""

import unittest
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models
from main import _enrichir_noms_exercices_prevus
from fastapi.testclient import TestClient
import main as main_module


def _setup_db_memoire():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.Base.metadata.create_all(bind=engine)
    return engine, TestSessionLocal


class TestEnrichirNomsExercicesPrevus(unittest.TestCase):
    def setUp(self):
        self.engine, self.TestSessionLocal = _setup_db_memoire()
        with self.TestSessionLocal() as db:
            db.add(models.ExerciceBibliotheque(id=1, nom="Développé couché", groupe_musculaire="pectoraux", type="force"))
            db.add(models.ExerciceBibliotheque(id=2, nom="Squat", groupe_musculaire="jambes", type="force"))
            db.commit()

    def test_ajoute_le_nom_par_exercice_id(self):
        with self.TestSessionLocal() as db:
            prevus = [
                {"exercice_id": 2, "series": 3, "repetitions": "8-10", "charge_indicative": "40 kg"},
                {"exercice_id": 1, "series": 3, "repetitions": "10", "charge_indicative": "20 kg"},
            ]
            resultat = _enrichir_noms_exercices_prevus(prevus, db)
        self.assertEqual(resultat[0]["nom"], "Squat")
        self.assertEqual(resultat[1]["nom"], "Développé couché")
        # Les champs d'origine restent intacts.
        self.assertEqual(resultat[0]["series"], 3)

    def test_exercice_id_inconnu_donne_nom_none(self):
        with self.TestSessionLocal() as db:
            resultat = _enrichir_noms_exercices_prevus([{"exercice_id": 999, "series": 1, "repetitions": "5"}], db)
        self.assertIsNone(resultat[0]["nom"])

    def test_liste_vide(self):
        with self.TestSessionLocal() as db:
            self.assertEqual(_enrichir_noms_exercices_prevus([], db), [])


class TestEndpointHistoriqueSeances(unittest.TestCase):
    """Tests d'intégration sur les vrais endpoints FastAPI, DB isolée en mémoire."""

    def setUp(self):
        self.engine, self.TestSessionLocal = _setup_db_memoire()

        def override_get_db():
            db = self.TestSessionLocal()
            try:
                yield db
            finally:
                db.close()

        main_module.app.dependency_overrides[main_module.get_db] = override_get_db
        self.client = TestClient(main_module.app)

        with self.TestSessionLocal() as db:
            db.add(models.ExerciceBibliotheque(id=1, nom="Développé couché", groupe_musculaire="pectoraux", type="force"))
            db.commit()

    def tearDown(self):
        main_module.app.dependency_overrides.clear()

    def test_get_historique_seances_enrichit_les_noms(self):
        with self.TestSessionLocal() as db:
            entry = models.HistoriqueSeance(
                date=date(2026, 8, 20),
                phase_calendaire="normale",
                type_seance="force",
                exercices_prevus=[{"exercice_id": 1, "series": 3, "repetitions": "8-10", "charge_indicative": "20 kg"}],
                exercices_realises=[{"exercice_id": 1, "nom": "Développé couché", "series": [{"numero_serie": 1, "poids_kg": 20.0, "repetitions": 9}]}],
                rpe=7,
                pourcentage_complete=100.0,
                etat_declare_avant={},
            )
            db.add(entry)
            db.commit()

        response = self.client.get("/api/historique_seances")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["exercices_prevus"][0]["nom"], "Développé couché")
        self.assertIsNone(data[0]["decision_adaptation"])

    def test_post_historique_seances_n_existe_plus(self):
        """Chemin client-writable retiré (aucun consommateur frontend, cf. audit Étape 2)."""
        response = self.client.post(
            "/api/historique_seances",
            json={"date": "2026-08-20", "type_seance": "force"},
        )
        self.assertEqual(response.status_code, 405)

    def test_liste_vide_si_aucune_seance(self):
        response = self.client.get("/api/historique_seances")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])


class TestChargeProgress(unittest.TestCase):
    """/api/progress/charge doit lire series_loggees (Étape 1), plus exercices_historique
    (legacy, jamais peuplée par le flux actuel)."""

    def setUp(self):
        self.engine, self.TestSessionLocal = _setup_db_memoire()

        def override_get_db():
            db = self.TestSessionLocal()
            try:
                yield db
            finally:
                db.close()

        main_module.app.dependency_overrides[main_module.get_db] = override_get_db
        self.client = TestClient(main_module.app)

        with self.TestSessionLocal() as db:
            db.add(models.ExerciceBibliotheque(id=1, nom="Développé couché", groupe_musculaire="pectoraux", type="force"))
            seance1 = models.Seance(id=1, date=date(2026, 8, 10), nom="S1", exercices=[])
            seance2 = models.Seance(id=2, date=date(2026, 8, 17), nom="S2", exercices=[])
            db.add_all([seance1, seance2])
            db.commit()
            db.add_all(
                [
                    models.SerieLoggee(seance_id=1, exercice_id=1, numero_serie=1, poids_kg=20.0, repetitions=10, coche=1),
                    models.SerieLoggee(seance_id=1, exercice_id=1, numero_serie=2, poids_kg=22.5, repetitions=8, coche=1),
                    # Série non cochée (annulée par l'utilisateur) : ne doit pas compter.
                    models.SerieLoggee(seance_id=1, exercice_id=1, numero_serie=3, poids_kg=100.0, repetitions=1, coche=0),
                    models.SerieLoggee(seance_id=2, exercice_id=1, numero_serie=1, poids_kg=25.0, repetitions=8, coche=1),
                ]
            )
            db.commit()

    def tearDown(self):
        main_module.app.dependency_overrides.clear()

    def test_retourne_charge_max_validee_par_seance(self):
        response = self.client.get("/api/progress/charge", params={"nom_exercice": "Développé couché"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data, [
            {"date": "2026-08-10", "loadKg": 22.5},
            {"date": "2026-08-17", "loadKg": 25.0},
        ])

    def test_exercice_inconnu_renvoie_liste_vide(self):
        response = self.client.get("/api/progress/charge", params={"nom_exercice": "Inexistant"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])


if __name__ == "__main__":
    unittest.main()
