"""Tests des transitions d'état critiques du parcours utilisateur : idempotence de la fin de
séance et de la génération de programme, conséquences d'une modification de profil.

Ce que ces tests protègent, côté produit :
- double tap sur « Terminer la séance » -> un seul historique, une seule fois l'XP ;
- double tap sur « Générer mon programme » -> un seul programme actif, pas de trame repartie
  de zéro sous les pieds de l'utilisateur ;
- une régénération explicitement demandée reste possible (sinon l'utilisateur serait bloqué
  avec un programme qui ne lui correspond plus) ;
- modifier ses disponibilités retire la séance du jour devenue incohérente SI elle n'a pas été
  commencée, et ne détruit jamais une séance déjà entamée ni l'historique passé.

Nécessite les dépendances du projet (sqlalchemy, fastapi) — voir requirements.txt. Comme les
autres tests d'intégration du dépôt (test_historique.py, test_etape6.py…), ce fichier échoue à
l'import si elles ne sont pas installées : limitation d'environnement, jamais contournée ici.

Lancer avec : python3 -m unittest test_idempotence_parcours -v (depuis backend/)
"""

import unittest
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

import models
import main as main_module

AUJOURDHUI = date(2026, 8, 26)  # un mercredi


def _setup_db_memoire():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.Base.metadata.create_all(bind=engine)
    return engine, TestSessionLocal


def _profil(**overrides):
    base = dict(
        id=1, objectifs=[], poste="Milieu", age=25, taille_cm=180.0, poids_kg=75.0,
        niveau_physique="intermediaire",
        niveaux_qualites_physiques={"force": 3, "explosivite": 3, "vitesse": 3, "endurance": 3},
        calendrier_matchs={"jour_habituel": None, "exceptions": []},
        contraintes_temps="45 min", materiel="salle complète",
        objectifs_v2=[{"theme": "force", "rang": 1, "poids": 0}],
        contexte_sportif={"sport": "football", "frequence_hebdo": 2, "poste": "Milieu"},
        disponibilites={
            "lundi": 60, "mardi": None, "mercredi": 60, "jeudi": None,
            "vendredi": 60, "samedi": None, "dimanche": None,
        },
    )
    base.update(overrides)
    return models.Profil(**base)


class _BaseApi(unittest.TestCase):
    def setUp(self):
        self.engine, self.TestSessionLocal = _setup_db_memoire()

        def override_get_db():
            db = self.TestSessionLocal()
            try:
                yield db
            finally:
                db.close()

        main_module.app.dependency_overrides[main_module.get_db] = override_get_db
        main_module.app.dependency_overrides[main_module.get_current_date] = lambda: AUJOURDHUI
        self.client = TestClient(main_module.app)

        # Aucun appel réseau dans ces tests : le programme retombe toujours sur le programme de
        # secours déterministe (_construire_programme_secours), ce qui est exactement le chemin
        # emprunté quand Mistral est indisponible.
        self._appel_mistral_original = main_module.mistral_client.appeler_mistral_json

        def _mistral_indisponible(prompt, system_prompt=None):
            raise main_module.mistral_client.MistralError("hors ligne (test)")

        main_module.mistral_client.appeler_mistral_json = _mistral_indisponible

    def tearDown(self):
        main_module.app.dependency_overrides.clear()
        main_module.mistral_client.appeler_mistral_json = self._appel_mistral_original


class TestFinDeSeanceIdempotente(_BaseApi):
    def setUp(self):
        super().setUp()
        with self.TestSessionLocal() as db:
            db.add(_profil())
            db.add(models.ExerciceBibliotheque(
                id=1, nom="Développé couché", groupe_musculaire="pectoraux", type="force",
                charge_recommandee="charge_lourde_progressive",
            ))
            db.add(models.Seance(
                id=1, date=AUJOURDHUI, nom="Séance force", statut="planifiee", type_seance="force",
                exercices=[{"exercice_id": 1, "series": 2, "repetitions": "8-10", "charge_indicative": "50 kg"}],
            ))
            db.add(models.SerieLoggee(
                seance_id=1, exercice_id=1, numero_serie=1, poids_kg=50.0, repetitions=10,
                reps_prevues=10, charge_prevue_kg=50.0, rpe_approx=7, difficulte="comme_prevu", coche=1,
            ))
            db.add(models.SerieLoggee(
                seance_id=1, exercice_id=1, numero_serie=2, poids_kg=50.0, repetitions=10,
                reps_prevues=10, charge_prevue_kg=50.0, rpe_approx=7, difficulte="comme_prevu", coche=1,
            ))
            db.commit()

    def _terminer(self):
        return self.client.post(
            "/api/seance/terminer",
            json={"seance_id": 1, "rpe": 7, "note": None, "duree_reelle_min": 45, "zone_sensible": None},
        )

    def test_double_appel_ne_cree_quun_seul_historique(self):
        premier = self._terminer()
        self.assertEqual(premier.status_code, 200, premier.text)
        second = self._terminer()
        self.assertEqual(second.status_code, 200, second.text)

        with self.TestSessionLocal() as db:
            self.assertEqual(db.query(models.HistoriqueSeance).count(), 1)

        self.assertEqual(second.json()["historique_id"], premier.json()["historique_id"])

    def test_double_appel_ne_double_pas_lxp(self):
        premier = self._terminer().json()
        second = self._terminer().json()
        self.assertEqual(second["xp_gagne"], premier["xp_gagne"])

        with self.TestSessionLocal() as db:
            xp_total = sum(h.xp_gagne or 0 for h in db.query(models.HistoriqueSeance).all())
        self.assertEqual(xp_total, premier["xp_gagne"])

    def test_second_appel_annonce_une_seance_deja_terminee(self):
        self._terminer()
        resume = self._terminer().json()["resume"]
        self.assertTrue(resume.get("deja_terminee"))
        # Le récapitulatif reste exploitable par l'écran de fin, pas une coquille vide.
        self.assertEqual(resume["nb_series_validees"], 2)
        self.assertEqual(resume["volume_total_kg"], 1000.0)

    def test_historique_est_lie_a_la_seance(self):
        self._terminer()
        with self.TestSessionLocal() as db:
            historique = db.query(models.HistoriqueSeance).one()
        self.assertEqual(historique.seance_id, 1)


class TestGenerationProgrammeIdempotente(_BaseApi):
    def setUp(self):
        super().setUp()
        with self.TestSessionLocal() as db:
            db.add(_profil())
            db.commit()

    def test_deux_generations_successives_renvoient_le_meme_programme(self):
        premier = self.client.post("/api/programme/generer", json={})
        self.assertEqual(premier.status_code, 200, premier.text)
        second = self.client.post("/api/programme/generer", json={})
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["id"], premier.json()["id"])

        with self.TestSessionLocal() as db:
            self.assertEqual(db.query(models.Programme).count(), 1)

    def test_regeneration_explicite_cree_un_nouveau_programme_actif(self):
        premier = self.client.post("/api/programme/generer", json={}).json()
        second = self.client.post("/api/programme/generer", json={"regenerer": True}).json()
        self.assertNotEqual(second["id"], premier["id"])

        with self.TestSessionLocal() as db:
            actifs = db.query(models.Programme).filter(models.Programme.statut == "actif").all()
            ancien = db.get(models.Programme, premier["id"])
        # Un seul programme actif à la fois : l'ancien est clôturé, jamais supprimé.
        self.assertEqual([p.id for p in actifs], [second["id"]])
        self.assertEqual(ancien.statut, "terminé")


class TestModificationProfil(_BaseApi):
    def setUp(self):
        super().setUp()
        with self.TestSessionLocal() as db:
            db.add(_profil())
            db.add(models.ExerciceBibliotheque(
                id=1, nom="Développé couché", groupe_musculaire="pectoraux", type="force",
                charge_recommandee="charge_lourde_progressive",
            ))
            db.commit()
        self.client.post("/api/programme/generer", json={})

    def _rendre_mercredi_indisponible(self):
        return self.client.patch(
            "/api/profil",
            json={"disponibilites": {
                "lundi": 60, "mardi": None, "mercredi": None, "jeudi": None,
                "vendredi": 60, "samedi": None, "dimanche": None,
            }},
        )

    def test_modification_recalcule_le_programme_et_le_dit(self):
        reponse = self._rendre_mercredi_indisponible()
        self.assertEqual(reponse.status_code, 200, reponse.text)
        corps = reponse.json()
        self.assertTrue(corps["programme_recalcule"])
        self.assertIsNone(corps["programme_erreur"])
        self.assertIsNone(corps["profil"]["disponibilites"]["mercredi"])

    def test_seance_du_jour_non_commencee_est_retiree_si_le_jour_devient_indisponible(self):
        with self.TestSessionLocal() as db:
            db.add(models.Seance(
                id=1, date=AUJOURDHUI, nom="Séance force", statut="planifiee", type_seance="force",
                exercices=[{"exercice_id": 1, "series": 3, "repetitions": "8-10"}],
            ))
            db.commit()

        corps = self._rendre_mercredi_indisponible().json()
        self.assertTrue(corps["seance_du_jour_supprimee"])
        with self.TestSessionLocal() as db:
            self.assertIsNone(db.get(models.Seance, 1))

    def test_seance_deja_commencee_nest_jamais_supprimee(self):
        with self.TestSessionLocal() as db:
            db.add(models.Seance(
                id=1, date=AUJOURDHUI, nom="Séance force", statut="planifiee", type_seance="force",
                exercices=[{"exercice_id": 1, "series": 3, "repetitions": "8-10"}],
            ))
            db.add(models.SerieLoggee(
                seance_id=1, exercice_id=1, numero_serie=1, poids_kg=50.0, repetitions=10, coche=1,
            ))
            db.commit()

        corps = self._rendre_mercredi_indisponible().json()
        self.assertFalse(corps["seance_du_jour_supprimee"])
        with self.TestSessionLocal() as db:
            self.assertIsNotNone(db.get(models.Seance, 1))

    def test_historique_passe_nest_pas_efface_par_une_modification(self):
        with self.TestSessionLocal() as db:
            db.add(models.HistoriqueSeance(
                date=date(2026, 8, 19), phase_calendaire="phase_normale", type_seance="force",
                exercices_prevus=[], exercices_realises=[], rpe=7, etat_declare_avant={},
            ))
            db.commit()

        self._rendre_mercredi_indisponible()
        with self.TestSessionLocal() as db:
            self.assertEqual(db.query(models.HistoriqueSeance).count(), 1)


if __name__ == "__main__":
    unittest.main()
