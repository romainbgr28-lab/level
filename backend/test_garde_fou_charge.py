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
from main import (
    _charge_prevue_depuis_indicative,
    _construire_charges_cibles,
    _construire_seance_secours,
    _corriger_charges_hors_tolerance,
    _derniere_charge_reelle,
)


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
            db.add(models.ExerciceBibliotheque(id=4, nom="Élévations latérales", groupe_musculaire="épaules", type="esthetique", charge_recommandee="charge_legere"))
            db.commit()

    def _log_seance_avec_charge(self, db, seance_id, exercice_id, poids_kg, jour):
        """Séance à une seule série cochée (poids_kg peut être un float unique)."""
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

    def _log_seance_avec_series(self, db, seance_id, exercice_id, poids_liste, jour, coches=None):
        """Séance avec plusieurs séries cochées pour le même exercice (échauffement, top
        set, drop set...). `coches` permet de marquer certaines séries comme non cochées."""
        db.add(models.Seance(id=seance_id, date=date(2026, 8, jour), nom="Séance", exercices=[]))
        for i, poids in enumerate(poids_liste):
            coche = 1 if coches is None else coches[i]
            db.add(
                models.SerieLoggee(
                    seance_id=seance_id,
                    exercice_id=exercice_id,
                    numero_serie=i + 1,
                    poids_kg=poids,
                    repetitions=8,
                    coche=coche,
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

    # --- Référence de charge : MAX des séries cochées de la dernière séance pertinente ---
    # (et non plus une moyenne, qui mélangeait à tort échauffement/top set/drop set)

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

    def test_derniere_charge_reelle_echauffement_puis_top_set_prend_le_max(self):
        with self.TestSessionLocal() as db:
            self._log_seance_avec_series(db, 1, 1, [40.0, 60.0, 70.0, 80.0], jour=1)
            reference = _derniere_charge_reelle(1, db)
        self.assertEqual(reference, 80.0)

    def test_derniere_charge_reelle_top_set_puis_drop_set_prend_le_max(self):
        with self.TestSessionLocal() as db:
            self._log_seance_avec_series(db, 1, 1, [60.0, 60.0, 55.0, 50.0], jour=1)
            reference = _derniere_charge_reelle(1, db)
        self.assertEqual(reference, 60.0)

    def test_derniere_charge_reelle_series_identiques(self):
        with self.TestSessionLocal() as db:
            self._log_seance_avec_series(db, 1, 1, [50.0, 50.0, 50.0], jour=1)
            reference = _derniere_charge_reelle(1, db)
        self.assertEqual(reference, 50.0)

    def test_derniere_charge_reelle_ignore_les_series_non_cochees_dans_le_lot(self):
        with self.TestSessionLocal() as db:
            # Le 999 non coché ne doit jamais influencer le MAX retenu.
            self._log_seance_avec_series(db, 1, 1, [40.0, 60.0, 999.0], jour=1, coches=[1, 1, 0])
            reference = _derniere_charge_reelle(1, db)
        self.assertEqual(reference, 60.0)

    # --- Arrondi de charge : granularité selon charge_recommandee, pas de plancher universel ---

    def test_arrondi_charge_moderee_lourde_conserve_arrondi_2_5kg(self):
        with self.TestSessionLocal() as db:
            # Squat = charge_lourde_progressive
            self._log_seance_avec_charge(db, 1, 1, 10.0, jour=1)
            plan = self._plan(1, db)
            cibles = _construire_charges_cibles(plan, 0.0, db)
        self.assertAlmostEqual(cibles[1], 10.0)

        with self.TestSessionLocal() as db:
            self._log_seance_avec_charge(db, 1, 1, 20.0, jour=1)
            plan = self._plan(1, db)
            cibles = _construire_charges_cibles(plan, 0.0, db)
        self.assertAlmostEqual(cibles[1], 20.0)

        with self.TestSessionLocal() as db:
            self._log_seance_avec_charge(db, 1, 1, 50.0, jour=1)
            plan = self._plan(1, db)
            cibles = _construire_charges_cibles(plan, 0.0, db)
        self.assertAlmostEqual(cibles[1], 50.0)

    def test_arrondi_charge_moderee_avec_ajustement_arrondit_a_2_5kg(self):
        with self.TestSessionLocal() as db:
            # Fentes (id 3) = charge_moderee ; 20 * 1.03 = 20.6 -> arrondi 2.5kg -> 20.0
            self._log_seance_avec_charge(db, 1, 3, 20.0, jour=1)
            plan = self._plan(3, db)
            cibles = _construire_charges_cibles(plan, 3.0, db)
        self.assertAlmostEqual(cibles[3], 20.0)

    def test_arrondi_charge_legere_petites_valeurs_sans_plancher_2_5kg(self):
        with self.TestSessionLocal() as db:
            # Élévations latérales (id 4) = charge_legere ; référence 1kg, pas d'ajustement.
            self._log_seance_avec_charge(db, 1, 4, 1.0, jour=1)
            plan = self._plan(4, db)
            cibles = _construire_charges_cibles(plan, 0.0, db)
        self.assertAlmostEqual(cibles[4], 1.0)  # jamais remonté à 2.5kg

        with self.TestSessionLocal() as db:
            self._log_seance_avec_charge(db, 1, 4, 3.0, jour=1)
            plan = self._plan(4, db)
            cibles = _construire_charges_cibles(plan, 0.0, db)
        self.assertAlmostEqual(cibles[4], 3.0)  # inchangé, pas remonté à un multiple de 2.5

    # --- Parsing de charge_indicative : strict, ne devine jamais sur formulation ambiguë ---

    def test_parsing_valeur_numerique_claire_avec_espace(self):
        self.assertEqual(_charge_prevue_depuis_indicative("20 kg"), 20.0)

    def test_parsing_valeur_numerique_claire_sans_espace(self):
        self.assertEqual(_charge_prevue_depuis_indicative("20kg"), 20.0)

    def test_parsing_decimale_virgule(self):
        self.assertEqual(_charge_prevue_depuis_indicative("17,5 kg"), 17.5)

    def test_parsing_haltere_ambigu_non_interprete_comme_2kg(self):
        # Piège explicite : "2 haltères de 10 kg" ne doit JAMAIS être lu comme 2kg.
        resultat = _charge_prevue_depuis_indicative("2 haltères de 10 kg")
        self.assertIsNone(resultat)
        self.assertNotEqual(resultat, 2.0)

    def test_parsing_haltere_ambigu_sans_espace_avant_kg(self):
        self.assertIsNone(_charge_prevue_depuis_indicative("2 haltères de 10kg"))

    def test_parsing_fourchette_tiret_ambigue(self):
        self.assertIsNone(_charge_prevue_depuis_indicative("20-22 kg"))

    def test_parsing_fourchette_a_ambigue(self):
        self.assertIsNone(_charge_prevue_depuis_indicative("20 à 22 kg"))

    def test_parsing_par_haltere_ambigu(self):
        self.assertIsNone(_charge_prevue_depuis_indicative("20 kg par haltère"))

    def test_parsing_texte_non_numerique_non_parsable(self):
        self.assertIsNone(_charge_prevue_depuis_indicative("charge modérée"))
        self.assertIsNone(_charge_prevue_depuis_indicative("à ajuster selon ressenti"))

    def test_parsing_poids_du_corps_conserve(self):
        self.assertIsNone(_charge_prevue_depuis_indicative("poids du corps"))

    def test_parsing_valeur_absente(self):
        self.assertIsNone(_charge_prevue_depuis_indicative(None))

    # --- Le garde-fou ne doit jamais corriger une valeur ambiguë/non interprétable ---

    def test_valeur_ambigue_non_ecrasee_par_le_garde_fou(self):
        with self.TestSessionLocal() as db:
            self._log_seance_avec_charge(db, 1, 1, 50.0, jour=1)
            plan = self._plan(1, db)
            cibles = _construire_charges_cibles(plan, 0.0, db)  # cible 50kg
            exercices = [{"exercice_id": 1, "charge_indicative": "2 haltères de 10 kg"}]
            _corriger_charges_hors_tolerance(exercices, cibles)
        # Ambigu : le garde-fou ne doit ni corriger, ni deviner 2kg.
        self.assertEqual(exercices[0]["charge_indicative"], "2 haltères de 10 kg")

    def test_valeur_fourchette_non_ecrasee_par_le_garde_fou(self):
        with self.TestSessionLocal() as db:
            self._log_seance_avec_charge(db, 1, 1, 50.0, jour=1)
            plan = self._plan(1, db)
            cibles = _construire_charges_cibles(plan, 0.0, db)  # cible 50kg
            exercices = [{"exercice_id": 1, "charge_indicative": "20-22 kg"}]
            _corriger_charges_hors_tolerance(exercices, cibles)
        self.assertEqual(exercices[0]["charge_indicative"], "20-22 kg")

    def test_valeur_descriptive_non_ecrasee_par_le_garde_fou(self):
        with self.TestSessionLocal() as db:
            self._log_seance_avec_charge(db, 1, 1, 50.0, jour=1)
            plan = self._plan(1, db)
            cibles = _construire_charges_cibles(plan, 0.0, db)  # cible 50kg
            exercices = [{"exercice_id": 1, "charge_indicative": "à ajuster selon ressenti"}]
            _corriger_charges_hors_tolerance(exercices, cibles)
        self.assertEqual(exercices[0]["charge_indicative"], "à ajuster selon ressenti")

    def test_valeur_numerique_claire_hors_tolerance_toujours_corrigee(self):
        with self.TestSessionLocal() as db:
            self._log_seance_avec_charge(db, 1, 1, 50.0, jour=1)
            plan = self._plan(1, db)
            cibles = _construire_charges_cibles(plan, 0.0, db)  # cible 50kg
            exercices = [{"exercice_id": 1, "charge_indicative": "90 kg"}]  # numérique, clair, hors tolérance
            _corriger_charges_hors_tolerance(exercices, cibles)
        self.assertEqual(exercices[0]["charge_indicative"], "50 kg")


class TestSeanceSecoursChargeCible(unittest.TestCase):
    """Chemin secours (Mistral indisponible) : doit utiliser directement la charge cible
    déterministe issue de _construire_charges_cibles (même source de vérité que le garde-fou
    du chemin Mistral, aucun second calcul) quand un historique réel existe, et conserver
    "à ajuster selon ressenti" faute de référence fiable — jamais de charge devinée."""

    def setUp(self):
        self.engine, self.TestSessionLocal = _setup_db_memoire()
        with self.TestSessionLocal() as db:
            db.add(models.ExerciceBibliotheque(id=1, nom="Squat", groupe_musculaire="jambes", type="force", charge_recommandee="charge_lourde_progressive"))
            db.add(models.ExerciceBibliotheque(id=5, nom="Développé couché", groupe_musculaire="pecs", type="force", charge_recommandee="charge_moderee"))
            db.add(models.ExerciceBibliotheque(id=6, nom="Gainage", groupe_musculaire="abdos", type="gainage_prevention", charge_recommandee="poids_du_corps"))
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

    def _plan(self, db, *ex_ids):
        exs = [db.get(models.ExerciceBibliotheque, ex_id) for ex_id in ex_ids]
        return [{"exercice": ex, "series": 3, "temps_repos_recommande_s": 90} for ex in exs]

    # --- A : historique réel + charge cible calculée -> charge numérique cible dans le secours ---

    def test_a_secours_avec_historique_reel_utilise_la_charge_cible(self):
        with self.TestSessionLocal() as db:
            self._log_seance_avec_charge(db, 1, 1, 50.0, jour=1)  # Squat, historique réel
            plan = self._plan(db, 1, 6)
            cibles = _construire_charges_cibles(plan, 0.0, db)  # cible Squat = 50kg
            data = _construire_seance_secours(plan, "force", rpe_cible=7, charges_cibles=cibles)
        squat = next(item for item in data["exercices"] if item["exercice_id"] == 1)
        self.assertEqual(squat["charge_indicative"], "50 kg")

    def test_a_bis_secours_avec_ajustement_positif_utilise_la_charge_cible_ajustee(self):
        with self.TestSessionLocal() as db:
            self._log_seance_avec_charge(db, 1, 1, 50.0, jour=1)
            plan = self._plan(db, 1)
            cibles = _construire_charges_cibles(plan, 10.0, db)  # 50 * 1.10 = 55kg
            data = _construire_seance_secours(plan, "force", rpe_cible=7, charges_cibles=cibles)
        self.assertEqual(data["exercices"][0]["charge_indicative"], "55 kg")

    # --- B : pas d'historique comparable / pas de cible -> "à ajuster selon ressenti" conservé ---

    def test_b_secours_sans_historique_conserve_texte_generique(self):
        with self.TestSessionLocal() as db:
            plan = self._plan(db, 5)  # Développé couché jamais loggé
            cibles = _construire_charges_cibles(plan, 0.0, db)  # vide : aucune référence
            data = _construire_seance_secours(plan, "force", rpe_cible=7, charges_cibles=cibles)
        self.assertEqual(data["exercices"][0]["charge_indicative"], "à ajuster selon ressenti")

    def test_b_bis_secours_sans_charges_cibles_du_tout_conserve_texte_generique(self):
        with self.TestSessionLocal() as db:
            plan = self._plan(db, 5)
            data = _construire_seance_secours(plan, "force", rpe_cible=7)  # charges_cibles omis
        self.assertEqual(data["exercices"][0]["charge_indicative"], "à ajuster selon ressenti")

    def test_secours_poids_du_corps_toujours_inchange(self):
        with self.TestSessionLocal() as db:
            plan = self._plan(db, 1, 6)
            cibles = _construire_charges_cibles(plan, 0.0, db)
            data = _construire_seance_secours(plan, "force", rpe_cible=7, charges_cibles=cibles)
        gainage = next(item for item in data["exercices"] if item["exercice_id"] == 6)
        self.assertEqual(gainage["charge_indicative"], "poids du corps")

    # --- C : chemin Mistral avec texte ambigu -> aucune correction (garde-fou inchangé) ---

    def test_c_mistral_texte_ambigu_aucune_correction(self):
        with self.TestSessionLocal() as db:
            self._log_seance_avec_charge(db, 1, 1, 50.0, jour=1)
            plan = self._plan(db, 1)
            cibles = _construire_charges_cibles(plan, 0.0, db)  # cible 50kg
            exercices = [{"exercice_id": 1, "charge_indicative": "2 haltères de 10 kg"}]
            _corriger_charges_hors_tolerance(exercices, cibles)
        self.assertEqual(exercices[0]["charge_indicative"], "2 haltères de 10 kg")

    # --- D : chemin Mistral avec charge numérique hors tolérance -> correction normale ---

    def test_d_mistral_charge_numerique_hors_tolerance_corrigee(self):
        with self.TestSessionLocal() as db:
            self._log_seance_avec_charge(db, 1, 1, 50.0, jour=1)
            plan = self._plan(db, 1)
            cibles = _construire_charges_cibles(plan, 0.0, db)  # cible 50kg
            exercices = [{"exercice_id": 1, "charge_indicative": "90 kg"}]
            _corriger_charges_hors_tolerance(exercices, cibles)
        self.assertEqual(exercices[0]["charge_indicative"], "50 kg")


if __name__ == "__main__":
    unittest.main()
