"""Tests du User Model V2 (Phase 8) : objectifs hiérarchisés, sport vs objectif,
disponibilités structurées, niveau déclaré/observé/effectif.

Utilise unittest (stdlib) plutôt que pytest : ce module (user_model_v2.py) n'a aucune
dépendance externe (pas de FastAPI/Pydantic/SQLAlchemy), donc ces tests peuvent tourner
même dans un environnement sans accès au registre de paquets. Les autres fichiers de test
du repo (test_regles_seance.py, etc.) utilisent pytest — cohérent avec le framework déjà
en place pour les tests touchant schemas.py/main.py directement.
"""

import unittest

import user_model_v2 as umv2


class TestObjectifsPoids(unittest.TestCase):
    def test_un_objectif_poids_1(self):
        result = umv2.normaliser_objectifs(["force"])
        self.assertEqual(result, [{"theme": "force", "rang": 1, "poids": 1.0}])

    def test_deux_objectifs_poids_60_30(self):
        result = umv2.normaliser_objectifs(["force", "endurance"])
        self.assertEqual([o["poids"] for o in result], [0.6, 0.3])
        self.assertEqual([o["rang"] for o in result], [1, 2])

    def test_trois_objectifs_poids_60_30_10(self):
        result = umv2.normaliser_objectifs(["force", "endurance", "discipline_mentale"])
        self.assertEqual([o["poids"] for o in result], [0.6, 0.3, 0.1])

    def test_plus_de_trois_objectifs_normalise_a_trois(self):
        result = umv2.normaliser_objectifs(
            ["force", "endurance", "discipline_mentale", "esthetique_hypertrophie"]
        )
        self.assertEqual(len(result), 3)
        self.assertEqual([o["theme"] for o in result], ["force", "endurance", "discipline_mentale"])

    def test_ancien_format_migre_correctement(self):
        result = umv2.normaliser_objectifs(["Force", "Endurance"])
        self.assertEqual(
            result,
            [
                {"theme": "force", "rang": 1, "poids": 0.6},
                {"theme": "endurance", "rang": 2, "poids": 0.3},
            ],
        )

    def test_ancien_libelle_esthetique_migre(self):
        result = umv2.normaliser_objectifs(["Hypertrophie/Esthétique"])
        self.assertEqual(result[0]["theme"], "esthetique_hypertrophie")

    def test_ancien_libelle_perte_de_poids_migre(self):
        result = umv2.normaliser_objectifs(["Perte de poids"])
        self.assertEqual(result[0]["theme"], "perte_de_gras")

    def test_ancien_libelle_performance_foot_migre(self):
        result = umv2.normaliser_objectifs(["Performance foot"])
        self.assertEqual(result[0]["theme"], "performance_sport_pratique")

    def test_ancien_libelle_inconnu_ignore_sans_crash(self):
        result = umv2.normaliser_objectifs(["Force", "Bidule inexistant"])
        self.assertEqual([o["theme"] for o in result], ["force"])

    def test_idempotent_sur_format_v2_deja_normalise(self):
        premier = umv2.normaliser_objectifs(["force", "endurance"])
        second = umv2.normaliser_objectifs(premier)
        self.assertEqual(premier, second)

    def test_liste_vide(self):
        self.assertEqual(umv2.normaliser_objectifs([]), [])
        self.assertEqual(umv2.normaliser_objectifs(None), [])

    def test_doublon_dedoublonne(self):
        result = umv2.normaliser_objectifs(["force", "force", "endurance"])
        self.assertEqual([o["theme"] for o in result], ["force", "endurance"])


class TestSportVsObjectif(unittest.TestCase):
    def test_sport_football_objectif_esthetique_pas_ajout_auto_performance(self):
        contexte = umv2.normaliser_contexte_sportif({"sport": "football"})
        objectifs = umv2.normaliser_objectifs(["esthetique_hypertrophie"])
        self.assertEqual(contexte["sport"], "football")
        self.assertEqual([o["theme"] for o in objectifs], ["esthetique_hypertrophie"])
        self.assertNotIn("performance_sport_pratique", [o["theme"] for o in objectifs])

    def test_sport_football_objectifs_esthetique_et_performance_tous_deux_presents(self):
        objectifs = umv2.normaliser_objectifs(["esthetique_hypertrophie", "performance_sport_pratique"])
        themes = [o["theme"] for o in objectifs]
        self.assertIn("esthetique_hypertrophie", themes)
        self.assertIn("performance_sport_pratique", themes)

    def test_sport_null_pas_de_contexte_football(self):
        contexte = umv2.normaliser_contexte_sportif({"sport": None})
        self.assertIsNone(contexte["sport"])
        self.assertEqual(umv2.obtenir_priorites(contexte["sport"], "Milieu"), [])

    def test_poste_ignore_si_pas_football(self):
        contexte = umv2.normaliser_contexte_sportif({"sport": "basket", "poste": "Ailier"})
        self.assertIsNone(contexte["poste"])

    def test_priorites_football_connu(self):
        self.assertEqual(
            umv2.obtenir_priorites("football", "Attaquant"),
            ["vitesse_linéaire", "explosivité_réactive", "finition_puissance"],
        )

    def test_priorites_sport_inconnu_fallback_generique(self):
        self.assertEqual(umv2.obtenir_priorites("basket", "Ailier"), [])

    def test_inference_legacy_football_depuis_poste(self):
        contexte = umv2.normaliser_contexte_sportif({}, poste_legacy="Milieu")
        self.assertEqual(contexte["sport"], "football")
        self.assertEqual(contexte["poste"], "Milieu")


class TestDisponibilites(unittest.TestCase):
    def test_dict_partiel_jours_disponibles_corrects(self):
        dispo = umv2.normaliser_disponibilites({"lundi": 60, "mercredi": 30})
        self.assertEqual(umv2.jours_dispo_abbrev(dispo), ["Lun", "Mer"])
        self.assertIsNone(dispo["mardi"])

    def test_valeur_null_explicite_indisponible(self):
        dispo = umv2.normaliser_disponibilites({"lundi": 60, "mardi": None})
        self.assertIsNone(dispo["mardi"])
        self.assertNotIn("Mar", umv2.jours_dispo_abbrev(dispo))

    def test_ancien_format_conversion_correcte(self):
        dispo = umv2.normaliser_disponibilites(None, fallback_contraintes_temps="Lun/Mer/Ven · 45 min/séance")
        self.assertEqual(dispo["lundi"], 45)
        self.assertEqual(dispo["mercredi"], 45)
        self.assertEqual(dispo["vendredi"], 45)
        self.assertIsNone(dispo["mardi"])
        self.assertEqual(umv2.jours_dispo_abbrev(dispo), ["Lun", "Mer", "Ven"])

    def test_ancien_format_invalide_ne_leve_pas(self):
        dispo = umv2.normaliser_disponibilites(None, fallback_contraintes_temps="n'importe quoi")
        self.assertEqual(dispo, umv2.disponibilites_vides())

    def test_toutes_les_7_cles_toujours_presentes(self):
        dispo = umv2.normaliser_disponibilites({"lundi": 60})
        self.assertEqual(set(dispo.keys()), set(umv2.JOURS_DISPONIBILITES))

    def test_idempotent(self):
        premier = umv2.normaliser_disponibilites({"lundi": 60, "mardi": None})
        second = umv2.normaliser_disponibilites(premier)
        self.assertEqual(premier, second)


class TestNiveau(unittest.TestCase):
    def test_aucune_donnee_historique_effectif_egal_declare(self):
        confiance = umv2.calculer_confiance(0)
        self.assertEqual(confiance, 0.0)
        effectif = umv2.calculer_niveau_effectif(3.0, None, confiance)
        self.assertEqual(effectif, 3.0)

    def test_peu_de_donnees_confiance_faible(self):
        confiance = umv2.calculer_confiance(1)
        self.assertLess(confiance, 0.2)

    def test_une_seule_mauvaise_seance_pas_de_bascule_brutale(self):
        # Une séance très ratée (RPE 9, complétion 40%) observée isolément.
        observe = umv2.calculer_niveau_observe([{"rpe": 9, "pourcentage_complete": 40}])
        confiance = umv2.calculer_confiance(1)
        effectif = umv2.calculer_niveau_effectif(4.0, observe, confiance)
        # Le niveau déclaré était 4 ; l'effectif doit rester proche du déclaré (confiance faible),
        # jamais s'effondrer d'un coup vers l'observé (ici bas, autour de 1.5-2.0).
        self.assertGreater(effectif, 3.0)

    def test_plusieurs_seances_coherentes_confiance_elevee(self):
        seances = [{"rpe": 6, "pourcentage_complete": 90} for _ in range(12)]
        observe = umv2.calculer_niveau_observe(seances)
        confiance = umv2.calculer_confiance(12)
        self.assertGreater(confiance, 0.8)
        effectif = umv2.calculer_niveau_effectif(2.0, observe, confiance)
        # Avec confiance élevée, l'effectif doit se rapprocher fortement de l'observé.
        self.assertLess(abs(effectif - observe), 0.6)

    def test_donnees_contradictoires_reste_dans_les_bornes(self):
        seances = [{"rpe": 2, "pourcentage_complete": 100}, {"rpe": 9, "pourcentage_complete": 30}]
        observe = umv2.calculer_niveau_observe(seances)
        self.assertIsNotNone(observe)
        self.assertGreaterEqual(observe, 1.0)
        self.assertLessEqual(observe, 5.0)

    def test_aucune_donnee_observee_est_none(self):
        self.assertIsNone(umv2.calculer_niveau_observe([]))
        self.assertIsNone(umv2.calculer_niveau_observe([{"rpe": None, "pourcentage_complete": None}]))

    def test_confiance_croissante_et_bornee(self):
        valeurs = [umv2.calculer_confiance(n) for n in (0, 1, 5, 10, 50, 1000)]
        for a, b in zip(valeurs, valeurs[1:]):
            self.assertLessEqual(a, b)
        self.assertLessEqual(valeurs[-1], 1.0)

    def test_confiance_ne_saute_jamais_a_10_seances_pile(self):
        # Pas de seuil brutal : la confiance à 9 et 11 séances doit être proche, pas un saut net.
        c9 = umv2.calculer_confiance(9)
        c11 = umv2.calculer_confiance(11)
        self.assertLess(abs(c11 - c9), 0.15)


if __name__ == "__main__":
    unittest.main()
