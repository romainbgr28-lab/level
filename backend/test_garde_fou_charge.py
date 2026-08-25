"""Tests de l'Étape 4 (garde-fou réel sur la charge) : le backend reste l'autorité finale
sur la charge quantitative quand un historique réel existe pour l'exercice, indépendamment
de ce que Mistral renvoie.

Nécessite les dépendances du projet (sqlalchemy, fastapi) — voir requirements.txt.
Lancer avec : python3 -m unittest backend.test_garde_fou_charge -v
(ou, depuis backend/ : python3 -m unittest test_garde_fou_charge -v)
"""

import unittest
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models
from main import _construire_charges_cibles, _corriger_charges_hors_tolerance, _derniere_charge_reelle


def _setup_db_memoire():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.Base.metadata.create_all(bind=engine)
    return engine, TestSessionLocal


class TestGardeFouCharge(unittest.TestCase):
    def setUp(self):
        self.engine, self.TestSessionLocal = _setup_db_memoire()
        with self.TestSessionLocal() as db:
            db.add(models.ExerciceBibliotheque(id=1, nom="Squat", groupe_musculaire="jambes", type="force", charge_recommandee="charge_lourde_progressive"))
            db.add(models.ExerciceBibliotheque(id=2, nom="Squat jump", groupe_musculaire="jambes", type="explosivite", charge_recommandee="poids_du_corps"))
            db.add(models.ExerciceBibliotheque(id=3, nom="Fentes", groupe_musculaire="jambes", type="force", charge_recommandee="charge_moderee"))
            db.commit()

    def _log_seance_avec_charge(self, db, seance_id, exercice_id, poids_kg, jour):
        db.add(models.Seance(id=seance_id, date=date(2026, 8, jour), nom="Séance", exercices=[]))
        db.add(
            models.SerieLoggee(
                seance_id=seance_id,
                exercice_id=exercice_id,
                numero_serie=1,
                poids_kg=poids_kg,
                repetitions=8,
                coche=1,
            )
        )
        db.commit()

    def _plan(self, ex_id, db):
        ex = db.get(models.ExerciceBibliotheque, ex_id)
        return [{"exercice": ex, "series": 3, "temps_repos_recommande_s": 90}]

    # --- A/B/C : calcul de charge_cible à partir de l'historique réel + ajustement ---

    def test_a_recommandation_neutre_aucune_correction(self):
        with self.TestSessionLocal() as db:
            self._log_seance_avec_charge(db, 1, 1, 50.0, jour=1)
            plan = self._plan(1, db)
            cibles = _construire_charges_cibles(plan, 0.0, db)
            exercices = [{"exercice_id": 1, "charge_indicative": "50 kg"}]
            _corriger_charges_hors_tolerance(exercices, cibles)
        self.assertEqual(exercices[0]["charge_indicative"], "50 kg")  # inchangé

    def test_b_recommandation_positive_charge_cible_appliquee(self):
        with self.TestSessionLocal() as db:
            self._log_seance_avec_charge(db, 1, 1, 50.0, jour=1)
            plan = self._plan(1, db)
            cibles = _construire_charges_cibles(plan, 10.0, db)  # +10%
        self.assertAlmostEqual(cibles[1], 55.0)

    def test_c_recommandation_negative_charge_cible_reduite(self):
        with self.TestSessionLocal() as db:
            self._log_seance_avec_charge(db, 1, 1, 50.0, jour=1)
            plan = self._plan(1, db)
            cibles = _construire_charges_cibles(plan, -10.0, db)  # -10%
        self.assertAlmostEqual(cibles[1], 45.0)

    # --- D/E : correction effective quand Mistral dévie de la cible hors tolérance ---

    def test_d_mistral_charge_trop_elevee_corrigee(self):
        with self.TestSessionLocal() as db:
            self._log_seance_avec_charge(db, 1, 1, 50.0, jour=1)
            plan = self._plan(1, db)
            cibles = _construire_charges_cibles(plan, 0.0, db)  # cible 50kg
            exercices = [{"exercice_id": 1, "charge_indicative": "80 kg"}]  # largement hors tolérance
            _corriger_charges_hors_tolerance(exercices, cibles)
        self.assertEqual(exercices[0]["charge_indicative"], "50 kg")

    def test_e_mistral_charge_trop_faible_corrigee_hors_tolerance(self):
        with self.TestSessionLocal() as db:
            self._log_seance_avec_charge(db, 1, 1, 50.0, jour=1)
            plan = self._plan(1, db)
            cibles = _construire_charges_cibles(plan, 0.0, db)  # cible 50kg, tolérance ±3.75kg
            exercices = [{"exercice_id": 1, "charge_indicative": "20 kg"}]  # hors tolérance
            _corriger_charges_hors_tolerance(exercices, cibles)
        self.assertEqual(exercices[0]["charge_indicative"], "50 kg")

    def test_e_bis_variation_legitime_dans_tolerance_non_corrigee(self):
        with self.TestSessionLocal() as db:
            self._log_seance_avec_charge(db, 1, 1, 50.0, jour=1)
            plan = self._plan(1, db)
            cibles = _construire_charges_cibles(plan, 0.0, db)  # cible 50kg, tolérance ±3.75kg
            exercices = [{"exercice_id": 1, "charge_indicative": "52.5 kg"}]  # dans la tolérance
            _corriger_charges_hors_tolerance(exercices, cibles)
        self.assertEqual(exercices[0]["charge_indicative"], "52.5 kg")

    # --- F : pas d'historique comparable -> aucune correction forcée ---

    def test_f_exercice_sans_historique_aucune_correction(self):
        with self.TestSessionLocal() as db:
            plan = self._plan(3, db)  # jamais loggé
            cibles = _construire_charges_cibles(plan, 10.0, db)
            exercices = [{"exercice_id": 3, "charge_indicative": "n'importe quoi"}]
            _corriger_charges_hors_tolerance(exercices, cibles)
        self.assertNotIn(3, cibles)
        self.assertEqual(exercices[0]["charge_indicative"], "n'importe quoi")  # inchangé

    # --- G : poids du corps -> comportement existant conservé (jamais dans charges_cibles) ---

    def test_g_exercice_poids_du_corps_jamais_cible(self):
        with self.TestSessionLocal() as db:
            self._log_seance_avec_charge(db, 1, 2, 0.0, jour=1)  # historique existe malgré tout
            plan = self._plan(2, db)
            cibles = _construire_charges_cibles(plan, 10.0, db)
        self.assertEqual(cibles, {})

    # --- H : la valeur persistée est bien la valeur corrigée ---

    def test_h_valeur_corrigee_est_celle_utilisee_pour_persistance(self):
        with self.TestSessionLocal() as db:
            self._log_seance_avec_charge(db, 1, 1, 50.0, jour=1)
            plan = self._plan(1, db)
            cibles = _construire_charges_cibles(plan, 8.0, db)  # 50 * 1.08 = 54 -> arrondi 2.5kg -> 55kg
            data_exercices = [{"exercice_id": 1, "series": 3, "repetitions": "8-10", "charge_indicative": "100 kg"}]
            _corriger_charges_hors_tolerance(data_exercices, cibles)
            seance = models.Seance(date=date(2026, 8, 20), nom="Séance test", exercices=data_exercices)
            db.add(seance)
            db.commit()
            db.refresh(seance)
            persiste = db.get(models.Seance, seance.id)
        self.assertEqual(persiste.exercices[0]["charge_indicative"], "55 kg")
        self.assertNotEqual(persiste.exercices[0]["charge_indicative"], "100 kg")

    # --- historique réel : dernière séance loggée sert de référence, moyenne des séries cochées ---

    def test_derniere_charge_reelle_prend_la_seance_la_plus_recente(self):
        with self.TestSessionLocal() as db:
            self._log_seance_avec_charge(db, 1, 1, 40.0, jour=1)
            self._log_seance_avec_charge(db, 2, 1, 50.0, jour=15)
            reference = _derniere_charge_reelle(1, db)
        self.assertEqual(reference, 50.0)

    def test_derniere_charge_reelle_ignore_series_non_cochees(self):
        with self.TestSessionLocal() as db:
            db.add(models.Seance(id=1, date=date(2026, 8, 1), nom="Séance", exercices=[]))
            db.add(models.SerieLoggee(seance_id=1, exercice_id=1, numero_serie=1, poids_kg=999.0, repetitions=8, coche=0))
            db.commit()
            reference = _derniere_charge_reelle(1, db)
        self.assertIsNone(reference)


if __name__ == "__main__":
    unittest.main()
