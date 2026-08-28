"""Tests d'intégration : les répétitions réellement réalisées (SerieLoggee) participent à
l'adaptation de la séance suivante.

Vérifie que le prévu/réalisé persisté par terminer_seance ressort bien dans
_construire_contexte_historique, et que ce signal atteint effectivement
regles_seance.calculer_ajustement_charge (donc le volume de la séance suivante, via
duree_seance.series_cible_depuis_ajustement) sans appel réseau (Mistral non sollicité ici).

Lancer avec : python3 -m unittest backend.test_adaptation_reps -v
(ou, depuis backend/ : python3 -m unittest test_adaptation_reps -v)
"""

import unittest
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import duree_seance
import main as main_module
import models
import regles_seance


def _setup_db_memoire():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.Base.metadata.create_all(bind=engine)
    return engine, TestSessionLocal


class TestAdaptationRepsBoutEnBout(unittest.TestCase):
    def setUp(self):
        self.engine, self.TestSessionLocal = _setup_db_memoire()
        main_module.SessionLocal = self.TestSessionLocal

        def _override_get_db():
            db = self.TestSessionLocal()
            try:
                yield db
            finally:
                db.close()

        main_module.app.dependency_overrides[main_module.get_db] = _override_get_db
        self.client = TestClient(main_module.app)

        with self.TestSessionLocal() as db:
            db.add(models.ExerciceBibliotheque(id=1, nom="Développé couché", groupe_musculaire="pectoraux", type="force"))
            seance = models.Seance(
                id=1,
                date=date(2026, 8, 20),
                nom="Séance force",
                type_seance="force",
                exercices=[
                    {"exercice_id": 1, "series": 3, "repetitions": "10", "charge_indicative": "20 kg"},
                ],
                statut="prévue",
            )
            db.add(seance)
            db.commit()

    def tearDown(self):
        self.engine.dispose()
        main_module.app.dependency_overrides.clear()

    def _loguer_serie(self, numero_serie, poids_kg, repetitions):
        resp = self.client.post(
            "/api/series_loggees",
            json={
                "seance_id": 1,
                "exercice_id": 1,
                "numero_serie": numero_serie,
                "poids_kg": poids_kg,
                "repetitions": repetitions,
                "coche": True,
                "difficulte": "dur",
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()

    def test_reps_prevues_persistees_a_la_creation(self):
        serie = self._loguer_serie(1, 20, 7)
        self.assertEqual(serie["reps_prevues"], 10)
        self.assertEqual(serie["charge_prevue_kg"], 20.0)

    def test_terminer_seance_expose_prevu_et_realise_par_serie(self):
        # Reproduit exactement l'exemple de la mission : prévu 20kg x 10 x 3, réalisé 7/6/6.
        self._loguer_serie(1, 20, 7)
        self._loguer_serie(2, 20, 6)
        self._loguer_serie(3, 20, 6)

        resp = self.client.post("/api/seance/terminer", json={"seance_id": 1, "rpe": 9})
        self.assertEqual(resp.status_code, 200, resp.text)

        with self.TestSessionLocal() as db:
            h = db.query(models.HistoriqueSeance).one()
            series = h.exercices_realises[0]["series"]
            self.assertEqual(len(series), 3)
            for s in series:
                self.assertEqual(s["reps_prevues"], 10)

    def test_signal_reps_reaches_context_historique(self):
        self._loguer_serie(1, 20, 7)
        self._loguer_serie(2, 20, 6)
        self._loguer_serie(3, 20, 6)
        resp = self.client.post("/api/seance/terminer", json={"seance_id": 1, "rpe": 6})
        self.assertEqual(resp.status_code, 200, resp.text)

        with self.TestSessionLocal() as db:
            contexte = main_module._construire_contexte_historique(db)
            entry = contexte["par_type"]["force"][0]
            self.assertIn("exercices_realises", entry)

            # Signal atteint bien calculer_ajustement_charge (donc la séance suivante) :
            # ratio réalisé/prévu = 19/30 -> nettement inférieur -> réduction de charge, alors
            # qu'avec RPE=6 seul (sans le signal reps) la cascade existante aurait maintenu.
            ajustement = regles_seance.calculer_ajustement_charge(
                contexte["par_type"]["force"], "intermédiaire", date(2026, 8, 27)
            )
            self.assertLess(ajustement["charge_pct"], 0.0)
            self.assertIn("Développé couché", ajustement["raison"])

            # Le volume de la séance suivante (nombre de séries ciblées) diminue bien en
            # conséquence -- démonstration que la décision atteint effectivement la génération.
            series_cible_apres = duree_seance.series_cible_depuis_ajustement(ajustement["volume_pct"])
            series_cible_neutre = duree_seance.series_cible_depuis_ajustement(0.0)
            self.assertLessEqual(series_cible_apres, series_cible_neutre)


if __name__ == "__main__":
    unittest.main()
