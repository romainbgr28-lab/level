"""Tests unitaires de la structure hebdomadaire déterministe du programme
(moteur_decision.construire_structure_hebdomadaire) — P1.0.

Lancer avec : python3 -m unittest test_structure_hebdomadaire -v (depuis backend/)
"""

import unittest

from moteur_decision import (
    construire_programme_secours,
    construire_structure_hebdomadaire,
    valider_gabarit_contre_structure,
)


def _obj(theme, rang, poids):
    return {"theme": theme, "rang": rang, "poids": poids}


DISPO_5J = {
    "lundi": 60, "mardi": None, "mercredi": 60, "jeudi": 60,
    "vendredi": 60, "samedi": None, "dimanche": 60,
}


class TestDominanteObjectifPrincipal(unittest.TestCase):
    def test_dominante_esthetique(self):
        objectifs = [
            _obj("esthetique_hypertrophie", 1, 0.6),
            _obj("perte_de_gras", 2, 0.3),
            _obj("performance_sport_pratique", 3, 0.1),
        ]
        structure = construire_structure_hebdomadaire(
            objectifs_v2=objectifs, sport="football", poste="Défenseur", disponibilites=DISPO_5J,
        )
        types = [info["type"] for info in structure.values()]
        self.assertGreater(types.count("esthétique"), types.count("force"))
        self.assertGreater(types.count("esthétique"), types.count("endurance"))
        self.assertIn("esthétique", types)

    def test_dominante_force(self):
        objectifs = [
            _obj("force", 1, 0.6),
            _obj("esthetique_hypertrophie", 2, 0.3),
            _obj("performance_sport_pratique", 3, 0.1),
        ]
        structure = construire_structure_hebdomadaire(
            objectifs_v2=objectifs, sport="football", poste="Défenseur", disponibilites=DISPO_5J,
        )
        types = [info["type"] for info in structure.values()]
        self.assertGreater(types.count("force"), types.count("esthétique"))

    def test_dominante_performance_sportive(self):
        objectifs = [
            _obj("performance_sport_pratique", 1, 0.6),
            _obj("esthetique_hypertrophie", 2, 0.3),
            _obj("perte_de_gras", 3, 0.1),
        ]
        structure = construire_structure_hebdomadaire(
            objectifs_v2=objectifs, sport="football", poste="Attaquant", disponibilites=DISPO_5J,
        )
        types = [info["type"] for info in structure.values()]
        # performance_sport_pratique -> explosivité_vitesse (pas d'endurance déclarée), dominante.
        self.assertGreaterEqual(types.count("explosivité_vitesse"), types.count("esthétique"))
        self.assertIn("explosivité_vitesse", types)


class TestPerteDeGrasTransversale(unittest.TestCase):
    def test_perte_de_gras_seule_ne_produit_pas_endurance(self):
        objectifs = [_obj("perte_de_gras", 1, 1.0)]
        structure = construire_structure_hebdomadaire(
            objectifs_v2=objectifs, sport=None, poste=None, disponibilites=DISPO_5J,
        )
        types = [info["type"] for info in structure.values()]
        self.assertNotIn("endurance", types)
        # Filet de sécurité final : "force" par défaut plutôt qu'un mapping perte_de_gras->endurance.
        self.assertTrue(all(t == "force" for t in types))


class TestSportNEcrasePasObjectif(unittest.TestCase):
    def test_football_esthetique_pas_ecrase_par_le_sport(self):
        objectifs = [_obj("esthetique_hypertrophie", 1, 1.0)]
        structure = construire_structure_hebdomadaire(
            objectifs_v2=objectifs, sport="football", poste="Milieu", disponibilites=DISPO_5J,
        )
        types = [info["type"] for info in structure.values()]
        self.assertTrue(all(t == "esthétique" for t in types))


class TestCalendrierMatch(unittest.TestCase):
    def test_veille_de_match_jamais_grosse_seance(self):
        objectifs = [_obj("force", 1, 1.0)]
        structure = construire_structure_hebdomadaire(
            objectifs_v2=objectifs, sport="football", poste="Défenseur",
            disponibilites=DISPO_5J, jour_match_habituel="Samedi",
        )
        self.assertIn("vendredi", structure)
        self.assertEqual(structure["vendredi"]["type"], "explosivité_vitesse")
        self.assertNotIn("samedi", structure)

    def test_lendemain_de_match_recuperation(self):
        objectifs = [_obj("force", 1, 1.0)]
        structure = construire_structure_hebdomadaire(
            objectifs_v2=objectifs, sport="football", poste="Défenseur",
            disponibilites=DISPO_5J, jour_match_habituel="Samedi",
        )
        self.assertEqual(structure["dimanche"]["type"], "repos")


class TestDisponibilites(unittest.TestCase):
    def test_jour_indisponible_aucune_seance(self):
        objectifs = [_obj("force", 1, 1.0)]
        structure = construire_structure_hebdomadaire(
            objectifs_v2=objectifs, sport=None, poste=None, disponibilites=DISPO_5J,
        )
        self.assertNotIn("mardi", structure)
        self.assertNotIn("samedi", structure)

    def test_aucune_disponibilite_aucun_entrainement(self):
        objectifs = [_obj("force", 1, 1.0)]
        dispo_vide = {j: None for j in DISPO_5J}
        structure = construire_structure_hebdomadaire(
            objectifs_v2=objectifs, sport=None, poste=None, disponibilites=dispo_vide,
        )
        self.assertEqual(structure, {})


class TestValidationMistralIncoherent(unittest.TestCase):
    def test_split_generique_mistral_est_corrige(self):
        """Simule ce que ferait main.py::generer_programme : un split générique renvoyé
        par Mistral (jours/type différents) est écrasé par la structure déterministe."""
        objectifs = [_obj("esthetique_hypertrophie", 1, 1.0)]
        structure = construire_structure_hebdomadaire(
            objectifs_v2=objectifs, sport="football", poste="Défenseur", disponibilites=DISPO_5J,
        )
        gabarit_generique_mistral = {
            "lundi": "force", "mercredi": "endurance", "jeudi": "explosivité_vitesse",
            "vendredi": "explosivité_vitesse", "dimanche": "repos",
        }
        gabarit_corrige, conforme = valider_gabarit_contre_structure(gabarit_generique_mistral, structure)
        self.assertFalse(conforme)
        self.assertEqual(gabarit_corrige, {jour: info["type"] for jour, info in structure.items()})
        self.assertNotIn("endurance", gabarit_corrige.values())


class TestFallback(unittest.TestCase):
    def test_fallback_structure_egale_structure_deterministe(self):
        objectifs = [_obj("force", 1, 0.6), _obj("esthetique_hypertrophie", 2, 0.3), _obj("perte_de_gras", 3, 0.1)]
        structure = construire_structure_hebdomadaire(
            objectifs_v2=objectifs, sport="football", poste="Défenseur", disponibilites=DISPO_5J,
        )
        programme_secours = construire_programme_secours(structure)
        self.assertEqual(
            programme_secours["gabarit_hebdomadaire"],
            {jour: info["type"] for jour, info in structure.items()},
        )


class TestCompatibiliteLegacy(unittest.TestCase):
    def test_profil_sans_objectifs_v2_ne_plante_pas(self):
        structure = construire_structure_hebdomadaire(
            objectifs_v2=None, sport="football", poste="Milieu", disponibilites=DISPO_5J,
            objectifs_legacy=["Force", "Endurance"],
        )
        self.assertTrue(structure)
        types = [info["type"] for info in structure.values()]
        self.assertTrue(set(types).issubset({"force", "endurance", "explosivité_vitesse", "esthétique", "repos"}))

    def test_profil_totalement_vide_ne_plante_pas(self):
        structure = construire_structure_hebdomadaire(
            objectifs_v2=None, sport=None, poste=None, disponibilites=DISPO_5J,
        )
        self.assertTrue(structure)
        types = [info["type"] for info in structure.values()]
        self.assertTrue(all(t == "force" for t in types))


class TestRangsInfluenceReelle(unittest.TestCase):
    def test_rang_1_influence_plus_que_rang_2_qui_influence_plus_que_rang_3(self):
        objectifs = [
            _obj("force", 1, 0.6),
            _obj("esthetique_hypertrophie", 2, 0.3),
            _obj("endurance", 3, 0.1),
        ]
        dispo_large = {
            "lundi": 60, "mardi": 60, "mercredi": 60, "jeudi": 60,
            "vendredi": 60, "samedi": None, "dimanche": 60,
        }
        structure = construire_structure_hebdomadaire(
            objectifs_v2=objectifs, sport=None, poste=None, disponibilites=dispo_large,
        )
        types = [info["type"] for info in structure.values()]
        self.assertGreater(types.count("force"), types.count("esthétique"))
        self.assertGreaterEqual(types.count("esthétique"), types.count("endurance"))

    def test_frequence_hebdo_ne_limite_plus_le_nombre_de_seances(self):
        """Régression du bug P1.0 : frequence_hebdo (fréquence du SPORT) ne doit plus plafonner
        le nombre de jours LEVEL — seules les disponibilités du profil font foi."""
        objectifs = [_obj("force", 1, 1.0)]
        structure = construire_structure_hebdomadaire(
            objectifs_v2=objectifs, sport=None, poste=None, disponibilites=DISPO_5J, frequence_hebdo=3,
        )
        self.assertEqual(len(structure), len(DISPO_5J) - 2)  # 5 jours dispo (mardi/samedi indispo)


class TestFrequenceHebdoNePlafonnePlusLevel(unittest.TestCase):
    """Bug P1.0 : contexte_sportif.frequence_hebdo décrit la fréquence de pratique du SPORT
    (ex. entraînements de football/semaine), pas le nombre de séances LEVEL voulues. Il ne doit
    jamais plafonner le nombre de jours retenus par construire_structure_hebdomadaire — c'est
    Profil.disponibilites qui fixe le plafond réel."""

    PROFIL_REEL_DISPO = {
        "lundi": 60, "mardi": None, "mercredi": 60, "jeudi": 60,
        "vendredi": 60, "samedi": None, "dimanche": 60,
    }

    def _objectifs_reels(self):
        return [
            _obj("perte_de_gras", 1, 0.6),
            _obj("esthetique_hypertrophie", 2, 0.3),
            _obj("performance_sport_pratique", 3, 0.1),
        ]

    def test_1_frequence_hebdo_1_ne_limite_pas_a_1_seance(self):
        structure = construire_structure_hebdomadaire(
            objectifs_v2=self._objectifs_reels(), sport="football", poste="Défenseur",
            disponibilites=self.PROFIL_REEL_DISPO, jour_match_habituel="samedi", frequence_hebdo=1,
        )
        self.assertGreater(len(structure), 1)

    def test_2_frequence_hebdo_2_ne_limite_pas_a_2_seances(self):
        structure = construire_structure_hebdomadaire(
            objectifs_v2=self._objectifs_reels(), sport="football", poste="Défenseur",
            disponibilites=self.PROFIL_REEL_DISPO, jour_match_habituel="samedi", frequence_hebdo=2,
        )
        self.assertGreater(len(structure), 2)

    def test_3_cinq_jours_disponibles_restent_disponibles_avec_frequence_hebdo_1(self):
        structure = construire_structure_hebdomadaire(
            objectifs_v2=self._objectifs_reels(), sport="football", poste="Défenseur",
            disponibilites=self.PROFIL_REEL_DISPO, jour_match_habituel="samedi", frequence_hebdo=1,
        )
        self.assertEqual(
            set(structure.keys()),
            {"lundi", "mercredi", "jeudi", "vendredi", "dimanche"},
        )

    def test_4_contraintes_match_samedi_conservees(self):
        structure = construire_structure_hebdomadaire(
            objectifs_v2=self._objectifs_reels(), sport="football", poste="Défenseur",
            disponibilites=self.PROFIL_REEL_DISPO, jour_match_habituel="samedi", frequence_hebdo=1,
        )
        self.assertNotIn("samedi", structure)  # jour de match : pas de séance LEVEL
        self.assertEqual(structure["vendredi"]["type"], "explosivité_vitesse")  # veille
        self.assertEqual(structure["dimanche"]["type"], "repos")  # lendemain

    def test_5_jour_indisponible_jamais_selectionne(self):
        structure = construire_structure_hebdomadaire(
            objectifs_v2=self._objectifs_reels(), sport="football", poste="Défenseur",
            disponibilites=self.PROFIL_REEL_DISPO, jour_match_habituel="samedi", frequence_hebdo=1,
        )
        self.assertNotIn("mardi", structure)

    def test_6_aucune_disponibilite_aucune_seance(self):
        dispo_vide = {j: None for j in self.PROFIL_REEL_DISPO}
        structure = construire_structure_hebdomadaire(
            objectifs_v2=self._objectifs_reels(), sport="football", poste="Défenseur",
            disponibilites=dispo_vide, jour_match_habituel="samedi", frequence_hebdo=1,
        )
        self.assertEqual(structure, {})

    def test_7_frequence_hebdo_reste_accessible_dans_le_contexte_sportif(self):
        from user_model_v2 import normaliser_contexte_sportif
        contexte = normaliser_contexte_sportif({"sport": "football", "frequence_hebdo": 1, "poste": "Défenseur"})
        self.assertIn("frequence_hebdo", contexte)
        self.assertEqual(contexte["frequence_hebdo"], 1)

    def test_8_objectifs_v2_hierarchises_toujours_respectes(self):
        objectifs = [
            _obj("force", 1, 0.6),
            _obj("esthetique_hypertrophie", 2, 0.3),
            _obj("performance_sport_pratique", 3, 0.1),
        ]
        structure = construire_structure_hebdomadaire(
            objectifs_v2=objectifs, sport="football", poste="Défenseur",
            disponibilites=self.PROFIL_REEL_DISPO, jour_match_habituel="samedi", frequence_hebdo=1,
        )
        types = [info["type"] for info in structure.values()]
        self.assertGreaterEqual(types.count("force"), types.count("esthétique"))

    def test_9_perte_de_gras_toujours_pas_automatiquement_endurance(self):
        structure = construire_structure_hebdomadaire(
            objectifs_v2=self._objectifs_reels(), sport="football", poste="Défenseur",
            disponibilites=self.PROFIL_REEL_DISPO, jour_match_habituel="samedi", frequence_hebdo=1,
        )
        types = [info["type"] for info in structure.values()]
        self.assertNotIn("endurance", types)

    def test_10_pas_de_regression_p05_types_valides(self):
        structure = construire_structure_hebdomadaire(
            objectifs_v2=self._objectifs_reels(), sport="football", poste="Défenseur",
            disponibilites=self.PROFIL_REEL_DISPO, jour_match_habituel="samedi", frequence_hebdo=1,
        )
        types = {info["type"] for info in structure.values()}
        self.assertTrue(types.issubset({"force", "explosivité_vitesse", "esthétique", "endurance", "repos"}))
        for jour, info in structure.items():
            self.assertTrue(info["objectif_principal"])


if __name__ == "__main__":
    unittest.main()
