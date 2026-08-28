"""Test d'intégration — correctif Étape 6 : la chaîne de remplacement A -> B (-> C) doit rester
exploitable ENTRE plusieurs séances, pas seulement à l'intérieur de la séance où le remplacement
a eu lieu.

Avant le correctif, generer_seance() initialisait toujours
exercices_seance_v2[i]["historique_exercice_ids"] à [] (main.py), même quand l'exercice du jour
était, en réalité, le successeur d'un exercice remplacé lors d'une séance précédente déjà
terminée. Résultat : adaptation_exercice.construire_historique_exercice(B, exercice_ids_lies=set())
ne retrouvait jamais l'historique antérieur de A, alors même que le lien B -> [A] était bien
persisté par terminer_seance() dans HistoriqueSeance.exercices_realises (via
/api/seance/{id}/remplacer_exercice).

Le correctif (main.py::_resoudre_chaine_remplacement, appelé depuis generer_seance()) reconstruit
cette chaîne à la volée à partir des HistoriqueSeance déjà persistées, sans toucher à
construire_historique_exercice / evaluer_exercice / composer (qui restent purs et inchangés).

Ce fichier NE fabrique jamais `historique_exercice_ids` à la main : chaque étape passe par le
vrai endpoint (/api/seance/generer, /api/seance/{id}/remplacer_exercice, /api/series_loggees,
/api/seance/terminer), pour reproduire le flux réel décrit par l'audit.

Nécessite les dépendances du projet (sqlalchemy, fastapi) — voir requirements.txt. Si elles ne
sont pas installées, ce fichier échoue à l'import (ModuleNotFoundError), comme les autres tests
d'intégration existants du dépôt (test_integration_v2_branchement.py, test_historique.py) : ce
n'est pas une régression introduite ici.

Lancer avec : python3 -m unittest test_remplacement_chaine_historique -v (depuis backend/)
"""

import unittest
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

import models
import main as main_module
import adaptation_exercice


def _setup_db_memoire():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.Base.metadata.create_all(bind=engine)
    return engine, TestSessionLocal


def _reponse_mistral(exercice_ids):
    """Fabrique une réponse Mistral factice qui ne fait que reprendre, tels quels, les
    exercice_id demandés (reps/RPE/charge sont gérés séparément via /api/series_loggees, pas
    par cette réponse -- ici on ne fait que peupler Seance.exercices)."""

    def _repondre(prompt, system_prompt=None):
        return {
            "nom_seance": "Séance test remplacement",
            "duree_min": 45,
            "explication": "généré par le test",
            "exercices": [
                {"exercice_id": eid, "series": 3, "repetitions": "10", "charge_indicative": "40 kg"}
                for eid in exercice_ids
            ],
        }

    return _repondre


class TestChaineRemplacementEntreSeances(unittest.TestCase):
    """A id=1, B id=2, C id=3 : même type/matériel, tous éligibles à chaque génération."""

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
        self._appel_mistral_original = main_module.mistral_client.appeler_mistral_json

        with self.TestSessionLocal() as db:
            for eid, nom in ((1, "Développé couché A"), (2, "Développé couché B"), (3, "Développé couché C")):
                db.add(models.ExerciceBibliotheque(
                    id=eid, nom=nom, groupe_musculaire="pectoraux", type="force",
                    charge_recommandee="charge_lourde_progressive",
                ))
            db.add(models.Profil(
                id=1, objectifs=[], poste="Milieu", age=25, taille_cm=180.0, poids_kg=75.0,
                niveau_physique="intermediaire",
                niveaux_qualites_physiques={"force": 3, "explosivite": 3, "vitesse": 3, "endurance": 3},
                calendrier_matchs={}, contraintes_temps="45 min", materiel="salle complète",
                objectifs_v2=[], contexte_sportif={"sport": "football"}, disponibilites={},
            ))
            db.commit()

    def tearDown(self):
        main_module.app.dependency_overrides.clear()
        main_module.mistral_client.appeler_mistral_json = self._appel_mistral_original

    def _set_date(self, d: date):
        main_module.app.dependency_overrides[main_module.get_current_date] = lambda: d

    def _generer(self):
        payload = {
            "sommeil": "bien", "motivation": "bien", "temps_dispo": "45 min",
            "envie_texte": "", "entrainement_club_semaine": "non",
        }
        return self.client.post("/api/seance/generer", json=payload)

    def _loguer_serie(self, seance_id, exercice_id, poids_kg=40.0, repetitions=10, rpe_approx=4):
        payload = {
            "seance_id": seance_id, "exercice_id": exercice_id, "numero_serie": 1,
            "poids_kg": poids_kg, "repetitions": repetitions, "coche": True, "rpe_approx": rpe_approx,
        }
        reponse = self.client.post("/api/series_loggees", json=payload)
        self.assertEqual(reponse.status_code, 200, reponse.text)

    def _terminer(self, seance_id):
        reponse = self.client.post("/api/seance/terminer", json={"seance_id": seance_id})
        self.assertEqual(reponse.status_code, 200, reponse.text)

    def test_cas2_remplacement_a_vers_b_retrouve_historique_de_a(self):
        """Scénario réel de l'audit : A performé et terminé, puis remplacé par B lors de la
        séance suivante (elle aussi performée et terminée), puis nouvelle génération : B doit
        bénéficier de l'historique de A, pas seulement du sien. Preuve observable : la confiance
        de la décision individuelle de B passe de CONFIANCE_MOYENNE (une seule occurrence, la
        sienne) à CONFIANCE_HAUTE (deux occurrences cohérentes : la sienne + celle de A), ce qui
        ne peut se produire QUE si construire_historique_exercice a bien reçu exercice_ids_lies
        contenant A."""
        # Séance 1 : A performé (reps atteintes, RPE bas -> tendance +1) puis terminée.
        self._set_date(date(2026, 8, 24))
        main_module.mistral_client.appeler_mistral_json = _reponse_mistral([1])
        seance1_id = self._generer().json()["id"]
        self._loguer_serie(seance1_id, exercice_id=1, poids_kg=40.0, repetitions=10, rpe_approx=4)
        self._terminer(seance1_id)

        # Séance 2 : A régénéré, remplacé par B via le vrai endpoint, B performé (même tendance
        # +1), séance terminée -> le lien B -> [A] est persisté par terminer_seance().
        self._set_date(date(2026, 8, 25))
        main_module.mistral_client.appeler_mistral_json = _reponse_mistral([1])
        seance2_id = self._generer().json()["id"]
        reponse_remplacement = self.client.post(
            f"/api/seance/{seance2_id}/remplacer_exercice",
            json={"exercice_id_actuel": 1, "exercice_id_nouveau": 2},
        )
        self.assertEqual(reponse_remplacement.status_code, 200, reponse_remplacement.text)
        self._loguer_serie(seance2_id, exercice_id=2, poids_kg=40.0, repetitions=10, rpe_approx=4)
        self._terminer(seance2_id)

        # Séance 3 : nouvelle génération automatique -- exercices_seance_v2 est construit
        # automatiquement par generer_seance(), aucune valeur fabriquée à la main ici.
        self._set_date(date(2026, 8, 26))
        main_module.mistral_client.appeler_mistral_json = _reponse_mistral([2])
        reponse3 = self._generer()
        self.assertEqual(reponse3.status_code, 200, reponse3.text)
        seance3_id = reponse3.json()["id"]

        with self.TestSessionLocal() as db:
            seance3 = db.get(models.Seance, seance3_id)
        par_exercice = seance3.decision_adaptation.get("par_exercice") or {}
        self.assertIn("2", par_exercice, "B (id=2) doit apparaître dans la décision individuelle de la séance 3")

        self.assertEqual(
            par_exercice["2"]["confiance"],
            adaptation_exercice.CONFIANCE_HAUTE,
            "La confiance de B doit refléter 2 occurrences cohérentes (la sienne + celle de A "
            "retrouvée via la chaîne de remplacement) -- si elle vaut CONFIANCE_MOYENNE, le "
            "correctif n'a pas fonctionné et seule l'occurrence de B a été trouvée.",
        )

    def test_cas3_remplacements_successifs_a_b_c(self):
        """A -> B -> C sur trois générations successives : C doit pouvoir retrouver la chaîne
        remontant jusqu'à A (au moins jusqu'à B, transitivement jusqu'à A), pas seulement B."""
        self._set_date(date(2026, 8, 10))
        main_module.mistral_client.appeler_mistral_json = _reponse_mistral([1])
        seance1_id = self._generer().json()["id"]
        self._loguer_serie(seance1_id, exercice_id=1, poids_kg=40.0, repetitions=10, rpe_approx=4)
        self._terminer(seance1_id)

        self._set_date(date(2026, 8, 11))
        main_module.mistral_client.appeler_mistral_json = _reponse_mistral([1])
        seance2_id = self._generer().json()["id"]
        self.client.post(
            f"/api/seance/{seance2_id}/remplacer_exercice",
            json={"exercice_id_actuel": 1, "exercice_id_nouveau": 2},
        )
        self._loguer_serie(seance2_id, exercice_id=2, poids_kg=40.0, repetitions=10, rpe_approx=4)
        self._terminer(seance2_id)

        self._set_date(date(2026, 8, 12))
        main_module.mistral_client.appeler_mistral_json = _reponse_mistral([2])
        seance3_id = self._generer().json()["id"]
        self.client.post(
            f"/api/seance/{seance3_id}/remplacer_exercice",
            json={"exercice_id_actuel": 2, "exercice_id_nouveau": 3},
        )
        self._loguer_serie(seance3_id, exercice_id=3, poids_kg=40.0, repetitions=10, rpe_approx=4)
        self._terminer(seance3_id)

        self._set_date(date(2026, 8, 13))
        main_module.mistral_client.appeler_mistral_json = _reponse_mistral([3])
        reponse4 = self._generer()
        self.assertEqual(reponse4.status_code, 200, reponse4.text)
        seance4_id = reponse4.json()["id"]

        with self.TestSessionLocal() as db:
            historique_ctx = main_module._construire_contexte_historique(db)
        chaine = main_module._resoudre_chaine_remplacement(3, historique_ctx["toutes"])
        self.assertIn(2, chaine, "C doit retrouver B comme prédécesseur immédiat")
        self.assertIn(1, chaine, "C doit retrouver A transitivement via B")

        with self.TestSessionLocal() as db:
            seance4 = db.get(models.Seance, seance4_id)
        par_exercice = seance4.decision_adaptation.get("par_exercice") or {}
        self.assertIn("3", par_exercice)
        self.assertEqual(par_exercice["3"]["confiance"], adaptation_exercice.CONFIANCE_HAUTE)

    def test_cas4_remplacement_ne_contamine_pas_un_autre_exercice(self):
        """Un remplacement A -> B sur un slot ne doit pas faire apparaître un historique lié
        pour un troisième exercice D totalement indépendant."""
        with self.TestSessionLocal() as db:
            db.add(models.ExerciceBibliotheque(
                id=4, nom="Développé couché D", groupe_musculaire="pectoraux", type="force",
                charge_recommandee="charge_lourde_progressive",
            ))
            db.commit()

        self._set_date(date(2026, 8, 10))
        main_module.mistral_client.appeler_mistral_json = _reponse_mistral([1])
        seance1_id = self._generer().json()["id"]
        self._loguer_serie(seance1_id, exercice_id=1, poids_kg=40.0, repetitions=10, rpe_approx=4)
        self._terminer(seance1_id)

        self._set_date(date(2026, 8, 11))
        main_module.mistral_client.appeler_mistral_json = _reponse_mistral([1])
        seance2_id = self._generer().json()["id"]
        self.client.post(
            f"/api/seance/{seance2_id}/remplacer_exercice",
            json={"exercice_id_actuel": 1, "exercice_id_nouveau": 2},
        )
        self._loguer_serie(seance2_id, exercice_id=2, poids_kg=40.0, repetitions=10, rpe_approx=4)
        self._terminer(seance2_id)

        with self.TestSessionLocal() as db:
            historique_ctx = main_module._construire_contexte_historique(db)
        chaine_d = main_module._resoudre_chaine_remplacement(4, historique_ctx["toutes"])
        self.assertEqual(chaine_d, [], "D est indépendant du remplacement A -> B : sa chaîne doit rester vide")

    def test_cas5_exercice_jamais_realise_comportement_inchange(self):
        """Un exercice jamais réalisé (ni lui, ni un quelconque prédécesseur) doit rester
        évalué comme 'jamais réalisé' (confiance nulle) -- aucune régression du cas existant."""
        self._set_date(date(2026, 8, 10))
        main_module.mistral_client.appeler_mistral_json = _reponse_mistral([3])
        reponse = self._generer()
        self.assertEqual(reponse.status_code, 200, reponse.text)
        seance_id = reponse.json()["id"]

        with self.TestSessionLocal() as db:
            seance = db.get(models.Seance, seance_id)
        par_exercice = seance.decision_adaptation.get("par_exercice") or {}
        self.assertIn("3", par_exercice)
        self.assertEqual(par_exercice["3"]["confiance"], adaptation_exercice.CONFIANCE_NULLE)


if __name__ == "__main__":
    unittest.main()
