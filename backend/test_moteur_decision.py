"""Tests unitaires du moteur de décision coaching (moteur_decision.py).

Lancer avec : python3 -m unittest test_moteur_decision -v (depuis backend/)
"""

import unittest
from datetime import date, timedelta

import regles_seance
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
        self.assertIn("force", decision.focus_principal)

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
        self.assertIn("VOICI LA DÉCISION DU COACH", section)
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


def _profil_objectif(theme_principal, theme_secondaire=None, sport="football", **overrides):
    objectifs_v2 = [{"theme": theme_principal, "rang": 1, "poids": 0.6 if theme_secondaire else 1.0}]
    if theme_secondaire:
        objectifs_v2.append({"theme": theme_secondaire, "rang": 2, "poids": 0.3})
    return _profil(objectifs_v2=objectifs_v2, contexte_sportif={"sport": sport, "frequence_hebdo": 3, "poste": "Milieu"}, **overrides)


class TestObjectifsV2PilotentReellementLeTypeDeSeance(unittest.TestCase):
    """P0.5 : l'objectif principal doit déterminer le type de séance, jamais le sport
    seul — voir regles_seance._suggerer_type_seance / user_model_v2.type_seance_pour_objectifs."""

    # TEST 1
    def test_objectif_hypertrophie_foot_donne_esthetique(self):
        profil = _profil_objectif("esthetique_hypertrophie", "performance_sport_pratique")
        decision = construire_decision(profil, _historique_vide(), {}, aujourdhui=AUJOURDHUI)
        self.assertEqual(decision.type_seance_recommande, "esthétique")
        self.assertEqual(decision.objectif_principal, "esthetique_hypertrophie")
        self.assertEqual(decision.objectif_secondaire, "performance_sport_pratique")

    # TEST 2
    def test_objectif_force_foot_donne_force(self):
        profil = _profil_objectif("force", "endurance")
        decision = construire_decision(profil, _historique_vide(), {}, aujourdhui=AUJOURDHUI)
        self.assertEqual(decision.type_seance_recommande, "force")

    # TEST 3
    def test_objectif_endurance_foot_donne_endurance(self):
        profil = _profil_objectif("endurance", "force")
        decision = construire_decision(profil, _historique_vide(), {}, aujourdhui=AUJOURDHUI)
        self.assertEqual(decision.type_seance_recommande, "endurance")

    # TEST 4
    def test_objectif_performance_sportive_foot_donne_type_oriente_performance(self):
        profil = _profil_objectif("performance_sport_pratique", "force")
        decision = construire_decision(profil, _historique_vide(), {}, aujourdhui=AUJOURDHUI)
        self.assertIn(decision.type_seance_recommande, ["explosivité_vitesse", "endurance"])

    def test_objectif_performance_sportive_avec_secondaire_endurance_choisit_endurance(self):
        profil = _profil_objectif("performance_sport_pratique", "endurance")
        decision = construire_decision(profil, _historique_vide(), {}, aujourdhui=AUJOURDHUI)
        self.assertEqual(decision.type_seance_recommande, "endurance")

    # TEST 5
    def test_hypertrophie_mais_match_demain_impose_seance_adaptee(self):
        profil = _profil_objectif(
            "esthetique_hypertrophie", "force", calendrier_matchs={"jour_habituel": "Jeudi", "exceptions": []}
        )
        decision = construire_decision(profil, _historique_vide(), {}, aujourdhui=AUJOURDHUI)
        # Veille de match -> le calendrier impose explosivité_vitesse (activation légère,
        # pas de séance esthétique/hypertrophie lourde), jamais "esthétique" ici.
        self.assertEqual(decision.type_seance_recommande, "explosivité_vitesse")
        self.assertNotEqual(decision.type_seance_recommande, "esthétique")
        self.assertEqual(decision.confiance_decision, 1.0)

    # TEST 6
    def test_force_lourde_mais_match_demain_ne_donne_pas_force_lourde(self):
        # Objectif principal "force" (séance lourde par défaut) mais match dès demain : le
        # calendrier doit imposer une séance adaptée (explosivité_vitesse, activation légère),
        # jamais la séance "force" que l'objectif seul aurait donnée (voir test 2).
        date_match = (AUJOURDHUI + timedelta(days=1)).isoformat()
        profil = _profil_objectif(
            "force", "endurance", calendrier_matchs={"jour_habituel": None, "exceptions": [{"date": date_match}]}
        )
        decision = construire_decision(profil, _historique_vide(), {}, aujourdhui=AUJOURDHUI)
        self.assertEqual(decision.type_seance_recommande, "explosivité_vitesse")
        self.assertNotEqual(decision.type_seance_recommande, "force")

    def test_approche_match_deux_jours_donne_explosivite_quel_que_soit_objectif(self):
        date_match = (AUJOURDHUI + timedelta(days=2)).isoformat()
        profil = _profil_objectif(
            "esthetique_hypertrophie", calendrier_matchs={"jour_habituel": None, "exceptions": [{"date": date_match}]}
        )
        decision = construire_decision(profil, _historique_vide(), {}, aujourdhui=AUJOURDHUI)
        self.assertEqual(decision.type_seance_recommande, "explosivité_vitesse")
        self.assertEqual(decision.confiance_decision, 1.0)

    # TEST 7
    def test_perte_de_gras_ne_force_pas_endurance_si_objectif_secondaire_tranche(self):
        profil = _profil_objectif("perte_de_gras", "force")
        decision = construire_decision(profil, _historique_vide(), {}, aujourdhui=AUJOURDHUI)
        self.assertEqual(decision.type_seance_recommande, "force")
        self.assertNotEqual(decision.type_seance_recommande, "endurance")

    def test_perte_de_gras_seul_retombe_sur_repli_legacy_pas_sur_endurance_arbitraire(self):
        profil = _profil_objectif("perte_de_gras")
        decision = construire_decision(profil, _historique_vide(), {}, aujourdhui=AUJOURDHUI)
        # Aucun thème exploitable -> repli force par défaut (jamais "endurance" inventé).
        self.assertEqual(decision.type_seance_recommande, "force")

    # TEST 8
    def test_ancien_profil_sans_objectifs_v2_aucun_crash_fallback_legacy(self):
        profil = {
            "poste": "Attaquant",
            "contexte_sportif": {"sport": "football"},
            "objectif_esthetique": {"tags": ["Silhouette générale"], "texte_libre": None},
            "materiel": "Aucun",
        }
        decision = construire_decision(profil, _historique_vide(), {}, aujourdhui=AUJOURDHUI)
        self.assertEqual(decision.type_seance_recommande, "esthétique")
        self.assertIsNone(decision.objectif_principal)

    # TEST 9 : le type décidé par DecisionCoaching est bien celui que generer_recommandation
    # renvoie (c'est cette même valeur que main.py::generer_seance utilise pour sélectionner
    # les exercices candidats -- voir main.py::_selectionner_exercices_candidats).
    def test_type_decision_identique_a_celui_de_generer_recommandation(self):
        profil = _profil_objectif("esthetique_hypertrophie", "performance_sport_pratique")
        historique = _historique_vide()
        etat = {}
        decision = construire_decision(profil, historique, etat, aujourdhui=AUJOURDHUI)
        recommandation = regles_seance.generer_recommandation(profil, historique, etat, aujourdhui=AUJOURDHUI)
        self.assertEqual(decision.type_seance_recommande, recommandation["type_seance_suggere"])
        self.assertEqual(decision.type_seance_recommande, "esthétique")

    # TEST 10 (intégration critique) : le sport ne doit jamais transformer silencieusement la
    # séance en séance football/explosivité alors que l'objectif principal est l'esthétique.
    def test_integration_critique_sport_football_objectif_esthetique_nest_pas_ecrase(self):
        for poste in ["Gardien", "Défenseur", "Milieu", "Attaquant"]:
            with self.subTest(poste=poste):
                profil = _profil_objectif("esthetique_hypertrophie", "performance_sport_pratique", poste=poste)
                profil["contexte_sportif"]["poste"] = poste
                recommandation = regles_seance.generer_recommandation(
                    profil, _historique_vide(), {}, aujourdhui=AUJOURDHUI
                )
                self.assertEqual(
                    recommandation["type_seance_suggere"],
                    "esthétique",
                    f"poste={poste} : le sport/poste football a écrasé l'objectif esthétique déclaré",
                )
                decision = construire_decision(profil, _historique_vide(), {}, aujourdhui=AUJOURDHUI)
                self.assertEqual(decision.type_seance_recommande, "esthétique")

    def test_formater_section_prompt_distingue_decision_et_generation(self):
        decision = construire_decision(_profil_objectif("force"), _historique_vide(), {}, aujourdhui=AUJOURDHUI)
        section = formater_section_prompt(decision)
        self.assertIn("VOICI LA DÉCISION DU COACH", section)
        self.assertIn("VOICI LES DÉTAILS À GÉNÉRER", section)
        self.assertIn("TYPE DE SÉANCE IMPOSÉ : force", section)
        self.assertIn("OBJECTIF PRINCIPAL : force", section)


if __name__ == "__main__":
    unittest.main()
