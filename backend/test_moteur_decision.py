"""Tests unitaires du moteur de décision coaching (moteur_decision.py).

Lancer avec : python3 -m unittest test_moteur_decision -v (depuis backend/)
"""

import unittest
from datetime import date, timedelta

from moteur_decision import construire_decision, formater_section_prompt

AUJOURDHUI = date(2026, 8, 26)  # mercredi


def _profil(**overrides):
    base = {
        "poste": "Milieu",
        "contexte_sportif": {"sport": "football", "frequence_hebdo": 3, "poste": "Milieu"},
        "objectifs_v2": [
            {"theme": "force", "rang": 1, "poids": 0.6},
            {"theme": "endurance", "rang": 2, "poids": 0.3},
            {"theme": "esthetique_hypertrophie", "rang": 3, "poids": 0.1},
        ],
        "disponibilites": {
            "lundi": 45, "mardi": None, "mercredi": 60, "jeudi": None,
            "vendredi": 45, "samedi": None, "dimanche": None,
        },
        "materiel": "Haltères",
        "calendrier_matchs": None,
    }
    base.update(overrides)
    return base


def _historique_vide():
    return {"par_type": {}, "recent": [], "zones_sensibles_recentes": []}


class TestConstruireDecisionCasNormal(unittest.TestCase):
    def test_objectifs_tries_par_rang(self):
        decision = construire_decision(_profil(), _historique_vide(), {}, aujourdhui=AUJOURDHUI)
        self.assertEqual(decision.objectifs_prioritaires, ["force", "endurance", "esthetique_hypertrophie"])

    def test_type_seance_recommande_present(self):
        decision = construire_decision(_profil(), _historique_vide(), {}, aujourdhui=AUJOURDHUI)
        self.assertIn(decision.type_seance_recommande, ["force", "explosivité_vitesse", "esthétique", "endurance", "décharge"])

    def test_qualites_prioritaires_depuis_poste(self):
        decision = construire_decision(_profil(), _historique_vide(), {}, aujourdhui=AUJOURDHUI)
        self.assertEqual(decision.qualites_prioritaires, ["endurance_intermittente", "coordination", "répétition_efforts"])

    def test_focus_utilise_objectif_principal(self):
        decision = construire_decision(_profil(), _historique_vide(), {}, aujourdhui=AUJOURDHUI)
        self.assertIn("force", decision.focus)

    def test_raisons_non_vides(self):
        decision = construire_decision(_profil(), _historique_vide(), {}, aujourdhui=AUJOURDHUI)
        self.assertTrue(decision.raisons)
        self.assertTrue(any("force" in r for r in decision.raisons))

    def test_contraintes_incluent_temps_dispo_du_jour(self):
        # AUJOURDHUI = mercredi -> 60 min de dispo dans _profil()
        decision = construire_decision(_profil(), _historique_vide(), {}, aujourdhui=AUJOURDHUI)
        self.assertTrue(any("60 min" in c for c in decision.contraintes))

    def test_contraintes_incluent_materiel(self):
        decision = construire_decision(_profil(), _historique_vide(), {}, aujourdhui=AUJOURDHUI)
        self.assertTrue(any("Haltères" in c for c in decision.contraintes))

    def test_formater_section_prompt_contient_strategie(self):
        decision = construire_decision(_profil(), _historique_vide(), {}, aujourdhui=AUJOURDHUI)
        section = formater_section_prompt(decision)
        self.assertIn("STRATÉGIE DE COACHING", section)
        self.assertIn(decision.type_seance_recommande, section)


class TestConstruireDecisionCalendrierMatch(unittest.TestCase):
    def test_veille_de_match_force_explosivite_vitesse(self):
        # AUJOURDHUI = mercredi 2026-08-26 ; jour_habituel = Jeudi -> match demain -> veille_match
        profil = _profil(calendrier_matchs={"jour_habituel": "Jeudi", "exceptions": []})
        decision = construire_decision(profil, _historique_vide(), {}, aujourdhui=AUJOURDHUI)
        self.assertEqual(decision.type_seance_recommande, "explosivité_vitesse")
        self.assertTrue(any("intensité maximale" in c for c in decision.contraintes))

    def test_approche_match_deux_jours_avant_force_explosivite_vitesse(self):
        date_match = (AUJOURDHUI + timedelta(days=2)).isoformat()
        profil = _profil(calendrier_matchs={"jour_habituel": None, "exceptions": [{"date": date_match}]})
        decision = construire_decision(profil, _historique_vide(), {}, aujourdhui=AUJOURDHUI)
        self.assertEqual(decision.type_seance_recommande, "explosivité_vitesse")
        self.assertTrue(any("intensité maximale" in c for c in decision.contraintes))


class TestConstruireDecisionDisponibilitesMaterielLimites(unittest.TestCase):
    def test_jour_sans_disponibilite_repli_sur_temps_dispo_etat_du_jour(self):
        profil = _profil(disponibilites={
            "lundi": None, "mardi": None, "mercredi": None, "jeudi": None,
            "vendredi": None, "samedi": None, "dimanche": None,
        })
        decision = construire_decision(
            profil, _historique_vide(), {"temps_dispo": "30 min"}, aujourdhui=AUJOURDHUI
        )
        self.assertTrue(any("30 min" in c for c in decision.contraintes))

    def test_materiel_aucun_toujours_dans_contraintes(self):
        profil = _profil(materiel="Aucun")
        decision = construire_decision(profil, _historique_vide(), {}, aujourdhui=AUJOURDHUI)
        self.assertTrue(any("Aucun" in c for c in decision.contraintes))

    def test_zones_sensibles_exclues(self):
        historique = {
            "par_type": {},
            "recent": [],
            "zones_sensibles_recentes": ["jambes"],
        }
        decision = construire_decision(_profil(), historique, {}, aujourdhui=AUJOURDHUI, type_seance_gabarit="force")
        self.assertTrue(any("jambes" in c for c in decision.contraintes))


class TestConstruireDecisionCompatibiliteAncienProfil(unittest.TestCase):
    def test_profil_sans_objectifs_v2_ni_disponibilites(self):
        """Profil ancien format : objectifs_v2/disponibilites absents (non normalisés côté
        appelant). Le moteur ne doit jamais lever, juste produire une décision plus pauvre."""
        profil = {
            "poste": "Attaquant",
            "contexte_sportif": {},
            "materiel": None,
        }
        decision = construire_decision(profil, _historique_vide(), {}, aujourdhui=AUJOURDHUI)
        self.assertEqual(decision.objectifs_prioritaires, [])
        self.assertIn("Aucun objectif V2 déclaré", " ".join(decision.raisons))
        self.assertIsInstance(decision.type_seance_recommande, str)
        # Ne doit pas planter le formatage du prompt non plus.
        section = formater_section_prompt(decision)
        self.assertIn("aucun objectif V2 déclaré", section)

    def test_profil_vide_ne_leve_jamais(self):
        decision = construire_decision({}, {}, {}, aujourdhui=AUJOURDHUI)
        self.assertIsInstance(decision.type_seance_recommande, str)
        self.assertIsInstance(decision.contraintes, list)

    def test_niveau_effectif_optionnel(self):
        decision = construire_decision(
            _profil(), _historique_vide(), {}, aujourdhui=AUJOURDHUI, niveau_effectif={"force": 3.4}
        )
        self.assertEqual(decision.niveau_effectif, {"force": 3.4})
        section = formater_section_prompt(decision)
        self.assertIn("force : 3.4", section)


if __name__ == "__main__":
    unittest.main()
