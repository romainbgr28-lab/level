"""Tests de l'Étape 1 (logging fiable par série) : prévu récupéré côté serveur, contrat
identique tap rapide / saisie manuelle, édition de la difficulté, compatibilité avec les
anciennes SerieLoggee sans prévu.

Nécessite les dépendances du projet (sqlalchemy, fastapi) — voir requirements.txt.
Lancer avec : python3 -m unittest backend.test_logging_serie -v
(ou, depuis backend/ : python3 -m unittest test_logging_serie -v)
"""

import unittest
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import database
import models
import schemas
from main import _charge_prevue_depuis_indicative, _prevu_pour_exercice, _reps_prevues_depuis_repetitions
from fastapi.testclient import TestClient
import main as main_module


class TestExtractionPrevu(unittest.TestCase):
    """Les fonctions d'extraction doivent suivre exactement les mêmes règles que
    repsCible/chargeCible côté frontend (Today.tsx)."""

    def test_reps_plage(self):
        self.assertEqual(_reps_prevues_depuis_repetitions("8-12"), 8)

    def test_reps_valeur_unique(self):
        self.assertEqual(_reps_prevues_depuis_repetitions("10"), 10)

    def test_reps_vide(self):
        self.assertIsNone(_reps_prevues_depuis_repetitions(None))
        self.assertIsNone(_reps_prevues_depuis_repetitions(""))

    def test_charge_numerique(self):
        self.assertEqual(_charge_prevue_depuis_indicative("20 kg"), 20.0)

    def test_charge_decimale_virgule(self):
        self.assertEqual(_charge_prevue_depuis_indicative("17,5 kg"), 17.5)

    def test_charge_poids_du_corps(self):
        self.assertIsNone(_charge_prevue_depuis_indicative("poids du corps"))

    def test_charge_texte_sans_nombre(self):
        self.assertIsNone(_charge_prevue_depuis_indicative("à ajuster selon ressenti"))

    def test_charge_none(self):
        self.assertIsNone(_charge_prevue_depuis_indicative(None))


class TestAssociationParExerciceId(unittest.TestCase):
    """L'association prévu <-> série doit se faire par exercice_id (champ explicite sur
    chaque item de Seance.exercices), jamais par position dans la liste."""

    def _seance(self, exercices):
        s = models.Seance(date=date(2026, 8, 25), nom="Test", exercices=exercices)
        return s

    def test_trouve_le_bon_exercice_meme_hors_ordre(self):
        seance = self._seance(
            [
                {"exercice_id": 7, "series": 3, "repetitions": "12-15", "charge_indicative": "poids du corps"},
                {"exercice_id": 3, "series": 3, "repetitions": "8-10", "charge_indicative": "20 kg"},
            ]
        )
        # exercice_id=3 est en 2e position : une association par index confondrait avec l'item 7.
        reps, charge = _prevu_pour_exercice(seance, 3)
        self.assertEqual(reps, 8)
        self.assertEqual(charge, 20.0)

    def test_exercice_absent_de_la_seance(self):
        seance = self._seance([{"exercice_id": 1, "series": 3, "repetitions": "10", "charge_indicative": "10 kg"}])
        reps, charge = _prevu_pour_exercice(seance, 999)
        self.assertIsNone(reps)
        self.assertIsNone(charge)

    def test_seance_none(self):
        reps, charge = _prevu_pour_exercice(None, 1)
        self.assertIsNone(reps)
        self.assertIsNone(charge)


def _setup_db_memoire():
    """Base SQLite en mémoire, isolée de backend/level.db, tables créées à la volée."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.Base.metadata.create_all(bind=engine)
    return engine, TestSessionLocal


class TestEndpointsSeriesLoggees(unittest.TestCase):
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
            exercice = models.ExerciceBibliotheque(
                nom="Développé couché",
                groupe_musculaire="pectoraux",
                type="force",
                charge_recommandee="charge_moderee",
            )
            db.add(exercice)
            db.commit()
            db.refresh(exercice)
            self.exercice_id = exercice.id

            seance = models.Seance(
                date=date(2026, 8, 25),
                nom="Séance test",
                exercices=[
                    {
                        "exercice_id": self.exercice_id,
                        "series": 3,
                        "repetitions": "8-10",
                        "charge_indicative": "20 kg",
                    }
                ],
                statut="planifiee",
            )
            db.add(seance)
            db.commit()
            db.refresh(seance)
            self.seance_id = seance.id

    def tearDown(self):
        main_module.app.dependency_overrides.clear()

    # TEST 1 : tap rapide -> prévu + réalisé + difficulté en DB
    def test_tap_rapide_persiste_prevu_et_reel(self):
        r = self.client.post(
            "/api/series_loggees",
            json={
                "seance_id": self.seance_id,
                "exercice_id": self.exercice_id,
                "numero_serie": 1,
                "poids_kg": 20,
                "repetitions": 8,
                "coche": True,
                "difficulte": "comme_prevu",
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["reps_prevues"], 8)
        self.assertEqual(body["charge_prevue_kg"], 20.0)
        self.assertEqual(body["repetitions"], 8)
        self.assertEqual(body["poids_kg"], 20)
        self.assertEqual(body["difficulte"], "comme_prevu")
        self.assertIsNotNone(body["rpe_approx"])

    # TEST 2 : saisie manuelle -> même résultat (même endpoint, même payload shape)
    def test_saisie_manuelle_meme_contrat(self):
        r = self.client.post(
            "/api/series_loggees",
            json={
                "seance_id": self.seance_id,
                "exercice_id": self.exercice_id,
                "numero_serie": 1,
                "poids_kg": 22.5,
                "repetitions": 7,
                "coche": True,
                "difficulte": "dur",
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["reps_prevues"], 8)
        self.assertEqual(body["charge_prevue_kg"], 20.0)
        self.assertEqual(body["repetitions"], 7)
        self.assertEqual(body["poids_kg"], 22.5)
        self.assertEqual(body["difficulte"], "dur")

    # TEST 3 : édition -> difficulté modifiable
    def test_edition_difficulte(self):
        created = self.client.post(
            "/api/series_loggees",
            json={
                "seance_id": self.seance_id,
                "exercice_id": self.exercice_id,
                "numero_serie": 1,
                "poids_kg": 20,
                "repetitions": 8,
                "coche": True,
                "difficulte": "facile",
            },
        ).json()

        r = self.client.patch(f"/api/series_loggees/{created['id']}", json={"difficulte": "dur"})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["difficulte"], "dur")
        # rpe_approx doit suivre la nouvelle difficulté (pas rester figé sur l'ancienne)
        self.assertNotEqual(body["rpe_approx"], created["rpe_approx"])
        # le prévu n'est pas affecté par une édition de la difficulté
        self.assertEqual(body["reps_prevues"], 8)
        self.assertEqual(body["charge_prevue_kg"], 20.0)

    # TEST 4 : anciennes SerieLoggee sans reps_prevues/charge_prevue -> aucun crash
    def test_ancienne_serie_sans_prevu_ne_casse_pas(self):
        with self.TestSessionLocal() as db:
            ancienne = models.SerieLoggee(
                seance_id=self.seance_id,
                exercice_id=self.exercice_id,
                numero_serie=1,
                poids_kg=18,
                repetitions=9,
                coche=1,
                difficulte="comme_prevu",
                rpe_approx=7,
                # reps_prevues / charge_prevue_kg volontairement omis (comme en prod avant migration)
            )
            db.add(ancienne)
            db.commit()
            ancienne_id = ancienne.id

        r = self.client.get(f"/api/series_loggees?seance_id={self.seance_id}")
        self.assertEqual(r.status_code, 200, r.text)
        serie = next(s for s in r.json() if s["id"] == ancienne_id)
        self.assertIsNone(serie["reps_prevues"])
        self.assertIsNone(serie["charge_prevue_kg"])
        self.assertEqual(serie["repetitions"], 9)

        # et elle reste éditable normalement
        r2 = self.client.patch(f"/api/series_loggees/{ancienne_id}", json={"poids_kg": 19})
        self.assertEqual(r2.status_code, 200, r2.text)
        self.assertEqual(r2.json()["poids_kg"], 19)

    # TEST 5 : le prévu correspond bien à l'exercice réellement logué, pas à un autre
    # exercice de la même séance (association par exercice_id, pas par position).
    def test_prevu_correspond_au_bon_exercice(self):
        with self.TestSessionLocal() as db:
            autre_exercice = models.ExerciceBibliotheque(
                nom="Squat", groupe_musculaire="jambes", type="force", charge_recommandee="charge_lourde_progressive"
            )
            db.add(autre_exercice)
            db.commit()
            db.refresh(autre_exercice)
            autre_id = autre_exercice.id

            seance = db.get(models.Seance, self.seance_id)
            seance.exercices = [
                {"exercice_id": autre_id, "series": 3, "repetitions": "5-6", "charge_indicative": "60 kg"},
                {"exercice_id": self.exercice_id, "series": 3, "repetitions": "8-10", "charge_indicative": "20 kg"},
            ]
            db.add(seance)
            db.commit()

        r = self.client.post(
            "/api/series_loggees",
            json={
                "seance_id": self.seance_id,
                "exercice_id": self.exercice_id,
                "numero_serie": 1,
                "poids_kg": 20,
                "repetitions": 8,
                "coche": True,
            },
        )
        body = r.json()
        self.assertEqual(body["reps_prevues"], 8)
        self.assertEqual(body["charge_prevue_kg"], 20.0)


if __name__ == "__main__":
    unittest.main()
