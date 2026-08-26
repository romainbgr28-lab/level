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

    def test_frequence_hebdo_limite_le_nombre_de_seances(self):
        objectifs = [_obj("force", 1, 1.0)]
        structure = construire_structure_hebdomadaire(
            objectifs_v2=objectifs, sport=None, poste=None, disponibilites=DISPO_5J, frequence_hebdo=3,
        )
        self.assertEqual(len(structure), 3)


if __name__ == "__main__":
    unittest.main()
