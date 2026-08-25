"""Tests de l'Étape 6 (audit et fiabilisation de la boucle d'adaptation) :

1. Plafonnement de rpe_cible par exercice à la valeur dérivée de intensite_max
   (_appliquer_calibrage_temps), sur le chemin Mistral comme sur le chemin secours.
2. Flux complet des zones sensibles : TerminerSeancePayload.zone_sensible ->
   HistoriqueSeance.zone_sensible_signalee -> _construire_contexte_historique ->
   zones_sensibles_recentes -> regles_seance.appliquer_garde_fous -> exclusions.

Nécessite les dépendances du projet (sqlalchemy, fastapi) — voir requirements.txt.
Lancer avec : python3 -m unittest backend.test_etape6 -v
(ou, depuis backend/ : python3 -m unittest test_etape6 -v)
"""

import unittest
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import main as main_module
import models
from main import ZONES_SENSIBLES_VALIDES, _appliquer_calibrage_temps, _construire_contexte_historique
from regles_seance import appliquer_garde_fous


def _setup_db_memoire():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.Base.metadata.create_all(bind=engine)
    return engine, TestSessionLocal


class TestClampRpeCible(unittest.TestCase):
    """_appliquer_calibrage_temps doit garantir rpe_final <= rpe_cible (dérivé de
    intensite_max par regles_seance/duree_seance.rpe_cible_pour_intensite, la seule
    source de vérité), sur les exercices renvoyés par Mistral comme par le secours."""

    def _plan(self, exercice_id=1, series=3, temps_repos=90):
        ex = models.ExerciceBibliotheque(id=exercice_id, nom="Squat", groupe_musculaire="jambes", type="force")
        return [{"exercice": ex, "series": series, "temps_repos_recommande_s": temps_repos}]

    # A. Mistral renvoie un RPE inférieur au plafond -> inchangé.
    def test_a_rpe_inferieur_au_plafond_inchange(self):
        plan = self._plan()
        exercices = [{"exercice_id": 1, "rpe_cible": 4}]
        _appliquer_calibrage_temps(exercices, plan, rpe_cible=6)
        self.assertEqual(exercices[0]["rpe_cible"], 4)

    # B. Mistral renvoie exactement le plafond -> inchangé.
    def test_b_rpe_egal_au_plafond_inchange(self):
        plan = self._plan()
        exercices = [{"exercice_id": 1, "rpe_cible": 6}]
        _appliquer_calibrage_temps(exercices, plan, rpe_cible=6)
        self.assertEqual(exercices[0]["rpe_cible"], 6)

    # C. Mistral renvoie au-dessus du plafond -> ramené au plafond.
    def test_c_rpe_superieur_au_plafond_corrige(self):
        plan = self._plan()
        exercices = [{"exercice_id": 1, "rpe_cible": 9}]
        _appliquer_calibrage_temps(exercices, plan, rpe_cible=6)
        self.assertEqual(exercices[0]["rpe_cible"], 6)

    # D. rpe_cible absent/non valide -> reprend le plafond (comportement actuel conservé).
    def test_d_rpe_absent_reprend_le_plafond(self):
        plan = self._plan()
        exercices = [{"exercice_id": 1}]
        _appliquer_calibrage_temps(exercices, plan, rpe_cible=6)
        self.assertEqual(exercices[0]["rpe_cible"], 6)

    def test_d_bis_rpe_non_entier_reprend_le_plafond(self):
        plan = self._plan()
        exercices = [{"exercice_id": 1, "rpe_cible": "élevé"}]
        _appliquer_calibrage_temps(exercices, plan, rpe_cible=6)
        self.assertEqual(exercices[0]["rpe_cible"], 6)

    def test_series_et_temps_repos_toujours_imposes(self):
        # Non-régression : le reste du garde-fou (series / temps de repos imposés depuis le
        # plan calibré côté serveur) doit continuer à fonctionner à l'identique.
        plan = self._plan(series=4, temps_repos=120)
        exercices = [{"exercice_id": 1, "series": 2, "temps_repos_recommande_s": 30, "rpe_cible": 3}]
        _appliquer_calibrage_temps(exercices, plan, rpe_cible=6)
        self.assertEqual(exercices[0]["series"], 4)
        self.assertEqual(exercices[0]["temps_repos_recommande_s"], 120)

    def test_exercice_absent_du_plan_ignore(self):
        plan = self._plan(exercice_id=1)
        exercices = [{"exercice_id": 999, "rpe_cible": 9}]
        _appliquer_calibrage_temps(exercices, plan, rpe_cible=6)
        # Exercice hors plan : jamais touché par le garde-fou.
        self.assertEqual(exercices[0]["rpe_cible"], 9)

    def test_chemin_secours_deja_conforme_au_plafond(self):
        """Le chemin secours (_construire_seance_secours) applique déjà rpe_cible de façon
        uniforme à tous les exercices : non-régression du comportement existant, pas de
        modification nécessaire de ce côté."""
        from main import _construire_seance_secours

        plan = self._plan()
        data = _construire_seance_secours(plan, "force", rpe_cible=6)
        self.assertEqual(data["exercices"][0]["rpe_cible"], 6)


class TestFluxZonesSensibles(unittest.TestCase):
    """Flux complet : TerminerSeancePayload.zone_sensible -> HistoriqueSeance.zone_sensible_signalee
    -> _construire_contexte_historique -> zones_sensibles_recentes -> appliquer_garde_fous
    -> exclusions."""

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

    def tearDown(self):
        main_module.app.dependency_overrides.clear()

    def _creer_seance_et_series(self, db, seance_id=1, exercice_id=1, jour=1):
        db.add(models.ExerciceBibliotheque(id=exercice_id, nom="Squat", groupe_musculaire="jambes", type="force"))
        db.add(
            models.Seance(
                id=seance_id,
                date=date(2026, 8, jour),
                nom="Séance",
                exercices=[{"exercice_id": exercice_id, "series": 3, "repetitions": "8-10"}],
                statut="en_cours",
            )
        )
        db.add(
            models.SerieLoggee(
                seance_id=seance_id,
                exercice_id=exercice_id,
                numero_serie=1,
                poids_kg=50.0,
                repetitions=8,
                coche=1,
            )
        )
        db.commit()

    def test_zone_sensible_valide_ecrite_dans_historique(self):
        with self.TestSessionLocal() as db:
            self._creer_seance_et_series(db)

        response = self.client.post(
            "/api/seance/terminer", json={"seance_id": 1, "zone_sensible": "jambes"}
        )
        self.assertEqual(response.status_code, 200)

        with self.TestSessionLocal() as db:
            entry = db.query(models.HistoriqueSeance).first()
            self.assertEqual(entry.zone_sensible_signalee, "jambes")

    def test_zone_sensible_aucune_donne_none(self):
        with self.TestSessionLocal() as db:
            self._creer_seance_et_series(db)

        response = self.client.post("/api/seance/terminer", json={"seance_id": 1, "zone_sensible": None})
        self.assertEqual(response.status_code, 200)

        with self.TestSessionLocal() as db:
            entry = db.query(models.HistoriqueSeance).first()
            self.assertIsNone(entry.zone_sensible_signalee)

    def test_zone_sensible_invalide_ignoree(self):
        """Une valeur hors ZONES_SENSIBLES_VALIDES ne doit jamais être enregistrée telle
        quelle (valeur contrôlée, pas de texte libre)."""
        with self.TestSessionLocal() as db:
            self._creer_seance_et_series(db)

        response = self.client.post(
            "/api/seance/terminer", json={"seance_id": 1, "zone_sensible": "n'importe quoi"}
        )
        self.assertEqual(response.status_code, 200)

        with self.TestSessionLocal() as db:
            entry = db.query(models.HistoriqueSeance).first()
            self.assertIsNone(entry.zone_sensible_signalee)

    def test_toutes_les_valeurs_controlees_sont_acceptees(self):
        for i, zone in enumerate(ZONES_SENSIBLES_VALIDES, start=1):
            with self.TestSessionLocal() as db:
                self._creer_seance_et_series(db, seance_id=i, exercice_id=100 + i, jour=i)
            response = self.client.post(
                "/api/seance/terminer", json={"seance_id": i, "zone_sensible": zone}
            )
            self.assertEqual(response.status_code, 200)
            with self.TestSessionLocal() as db:
                entry = db.query(models.HistoriqueSeance).filter_by(date=date(2026, 8, i)).first()
                self.assertEqual(entry.zone_sensible_signalee, zone)

    def test_contexte_historique_reprend_la_zone_signalee(self):
        with self.TestSessionLocal() as db:
            self._creer_seance_et_series(db)
        self.client.post("/api/seance/terminer", json={"seance_id": 1, "zone_sensible": "épaules"})

        with self.TestSessionLocal() as db:
            contexte = _construire_contexte_historique(db)
        self.assertIn("épaules", contexte["zones_sensibles_recentes"])

    def test_exclusion_generee_pour_type_de_seance_concerne(self):
        # "force" sollicite notamment "épaules" (regles_seance.GROUPES_PAR_TYPE_SEANCE) :
        # une zone sensible "épaules" déclarée doit se retrouver dans les exclusions.
        recommandation = {"type_seance_suggere": "force", "ajustement_volume_pct": 0.0}
        reco, raisons = appliquer_garde_fous(
            recommandation,
            zones_sensibles=["épaules"],
            entrainements_club_semaine=0,
            seance_prevue_meme_jour_club=False,
            historique_recent=[],
        )
        self.assertIn("épaules", reco["exclusions"])
        self.assertTrue(any("épaules" in r for r in raisons))

    def test_pas_d_exclusion_si_zone_non_concernee_par_le_type_de_seance(self):
        # "endurance" ne sollicite que "jambes" (GROUPES_PAR_TYPE_SEANCE) : une zone sensible
        # "bras" déclarée ne doit pas générer d'exclusion pour ce type de séance précis.
        recommandation = {"type_seance_suggere": "endurance", "ajustement_volume_pct": 0.0}
        reco, raisons = appliquer_garde_fous(
            recommandation,
            zones_sensibles=["bras"],
            entrainements_club_semaine=0,
            seance_prevue_meme_jour_club=False,
            historique_recent=[],
        )
        self.assertEqual(reco["exclusions"], [])

    def test_flux_complet_bout_en_bout(self):
        """Bout en bout : zone déclarée en fin de séance -> reprise par le contexte
        historique -> exclusion effective produite par le moteur de règles pour un type de
        séance concerné."""
        with self.TestSessionLocal() as db:
            self._creer_seance_et_series(db)
        self.client.post("/api/seance/terminer", json={"seance_id": 1, "zone_sensible": "jambes"})

        with self.TestSessionLocal() as db:
            contexte = _construire_contexte_historique(db)

        recommandation = {"type_seance_suggere": "force", "ajustement_volume_pct": 0.0}
        reco, _ = appliquer_garde_fous(
            recommandation,
            zones_sensibles=contexte["zones_sensibles_recentes"],
            entrainements_club_semaine=0,
            seance_prevue_meme_jour_club=False,
            historique_recent=[],
        )
        self.assertIn("jambes", reco["exclusions"])


if __name__ == "__main__":
    unittest.main()
