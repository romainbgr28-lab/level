"""Tests de la boucle d'orchestration du coach (coach.py).

Le LLM est remplacé par un modèle factice scripté : aucune clé API, aucun réseau. Tout le
reste est réel — les actions s'exécutent et écrivent vraiment en base. C'est précisément ce
qui rend ces tests utiles : ils vérifient la règle structurante de la V0 (section 18), à
savoir que **le LLM n'est pas le moteur de décision**.

Ce qu'ils protègent :
- un modèle qui « raconte » une séance sans appeler d'outil n'écrit rien en base ;
- un modèle qui demande une action déclenche une vraie écriture métier ;
- le catalogue d'outils exposé au modèle est exactement le registre d'actions (pas d'outil
  fantôme, pas d'action inaccessible) ;
- des arguments malformés ou une boucle qui s'emballe ne cassent pas la conversation ;
- la conversation est persistée, mais reste secondaire : la mémoire est en base.

Nécessite les dépendances du projet (sqlalchemy, fastapi, pydantic) — voir requirements.txt.

Lancer avec : python3 -m unittest test_coach_orchestration -v (depuis backend/)
"""

import json
import unittest
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import coach
import coach_actions
import main as main_module
import models

AUJOURDHUI = date(2026, 9, 16)  # un mercredi


def _appel(nom, arguments, identifiant="call_1"):
    return {
        "id": identifiant,
        "type": "function",
        "function": {"name": nom, "arguments": json.dumps(arguments)},
    }


class _LLMFactice:
    """Modèle scripté : renvoie les messages fournis, dans l'ordre, un par tour.

    Enregistre les `messages` reçus pour que les tests puissent vérifier ce que le modèle a
    réellement vu (contexte injecté, résultats d'outils réinjectés).
    """

    def __init__(self, reponses):
        self.reponses = list(reponses)
        self.appels_recus = []

    def __call__(self, messages, tools):
        self.appels_recus.append({"messages": list(messages), "tools": tools})
        if not self.reponses:
            return {"role": "assistant", "content": "Terminé.", "tool_calls": []}
        return self.reponses.pop(0)


class _BaseOrchestration(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        self.TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        models.Base.metadata.create_all(bind=self.engine)
        self.db = self.TestSessionLocal()

        self._appel_original = main_module.mistral_client.appeler_mistral_json

        def _mistral_indisponible(prompt, system_prompt=None):
            raise main_module.mistral_client.MistralError("hors ligne (test)")

        main_module.mistral_client.appeler_mistral_json = _mistral_indisponible

        self.db.add(models.Profil(
            id=1, objectifs=[], poste="Milieu", age=25, taille_cm=180.0, poids_kg=75.0,
            niveau_physique="intermediaire",
            niveaux_qualites_physiques={"force": 3, "explosivite": 3, "vitesse": 3, "endurance": 3},
            calendrier_matchs={"jour_habituel": "Samedi", "exceptions": [], "annulations": []},
            contraintes_temps="60 min", materiel="Salle complète",
            objectifs_v2=[{"theme": "force", "rang": 1, "poids": 0.6}],
            contexte_sportif={"sport": "football", "frequence_hebdo": 2, "poste": "Milieu"},
            disponibilites={"lundi": 60, "mardi": None, "mercredi": 60, "jeudi": None,
                            "vendredi": 60, "samedi": None, "dimanche": None},
        ))
        self.db.add(models.ExerciceBibliotheque(
            id=1, nom="Développé incliné haltères", groupe_musculaire="pectoraux", type="force",
            materiel_requis="haltères et banc", materiel_requis_liste=["halteres", "banc"],
            pattern_mouvement="poussee_horizontale", groupe_musculaire_principal="pectoraux",
            charge_recommandee="charge_lourde_progressive",
        ))
        # Programme actif : sans lui, le contexte du jour vaut « aucun_programme » quoi qu'il
        # arrive, et ces tests ne verraient jamais l'état nominal qu'ils décrivent.
        self.db.add(models.Programme(
            id=1, utilisateur_id=1, date_debut=AUJOURDHUI, duree_semaines=8,
            phases=[{"nom": "adaptation", "semaine_debut": 1, "semaine_fin": 8, "description": "Reprise."}],
            gabarit_hebdomadaire={"Lun": "force", "Mer": "force", "Ven": "explosivité_vitesse"},
            trajectoire_progression={"force": [100.0] * 8}, statut="actif",
        ))
        self.db.add(models.Seance(
            id=1, date=AUJOURDHUI, nom="Haut du corps", statut="planifiee", type_seance="force",
            duree_prevue=50,
            exercices=[{"exercice_id": 1, "series": 4, "repetitions": "8", "charge_indicative": "24 kg"}],
        ))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        main_module.mistral_client.appeler_mistral_json = self._appel_original

    def repondre(self, message, reponses_llm):
        llm = _LLMFactice(reponses_llm)
        resultat = coach.repondre(self.db, AUJOURDHUI, message, appel_llm=llm)
        return resultat, llm


class TestCatalogueOutils(unittest.TestCase):
    def test_outils_et_actions_alignes(self):
        """Un outil sans action derrière serait un outil qui échoue systématiquement ; une
        action sans outil serait une capacité que le coach ne peut jamais utiliser."""
        noms_outils = {o["function"]["name"] for o in coach.OUTILS}

        self.assertEqual(noms_outils, set(coach_actions.ACTIONS))

    def test_chaque_outil_a_un_schema_exploitable(self):
        for outil in coach.OUTILS:
            fonction = outil["function"]
            with self.subTest(outil=fonction["name"]):
                self.assertTrue(fonction["description"].strip())
                self.assertEqual(fonction["parameters"]["type"], "object")
                proprietes = fonction["parameters"]["properties"]
                for requis in fonction["parameters"]["required"]:
                    self.assertIn(requis, proprietes, "un paramètre requis doit être déclaré")


class TestLeLLMNestPasLeMoteur(_BaseOrchestration):
    def test_une_reponse_sans_outil_n_ecrit_rien(self):
        """Un modèle qui improvise « c'est enregistré ! » ne doit RIEN pouvoir écrire :
        il n'a aucun chemin vers la base en dehors des outils."""
        resultat, _ = self.repondre(
            "J'ai fait 24 kg, 4x8 au développé incliné.",
            [{"role": "assistant", "content": "C'est enregistré, 24 kg sur 4x8 !", "tool_calls": []}],
        )

        self.assertEqual(resultat["actions"], [])
        self.assertEqual(self.db.query(models.SerieLoggee).count(), 0)

    def test_une_action_demandee_ecrit_reellement(self):
        resultat, _ = self.repondre(
            "J'ai fait 24 kg, 4x8 au développé incliné, c'était facile.",
            [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [_appel("enregistrer_performance", {
                        "nom": "développé incliné", "series": 4, "repetitions": 8,
                        "charge_kg": 24, "difficulte": "facile",
                    })],
                },
                {"role": "assistant", "content": "C'est enregistré. 24 kg sur 4x8, facile.", "tool_calls": []},
            ],
        )

        self.assertEqual(len(resultat["actions"]), 1)
        self.assertTrue(resultat["actions"][0]["resultat"]["ok"])
        self.assertEqual(self.db.query(models.SerieLoggee).count(), 4)
        self.assertEqual(resultat["reponse"], "C'est enregistré. 24 kg sur 4x8, facile.")

    def test_le_resultat_de_l_action_est_reinjecte_au_modele(self):
        """Sans ça, le modèle formulerait sa réponse sans savoir ce que le moteur a décidé."""
        _, llm = self.repondre(
            "Je n'ai que 25 minutes.",
            [
                {"role": "assistant", "content": "",
                 "tool_calls": [_appel("adapter_seance", {"motif": "duree", "minutes_disponibles": 25})]},
                {"role": "assistant", "content": "D'accord, je raccourcis.", "tool_calls": []},
            ],
        )

        messages_second_tour = llm.appels_recus[1]["messages"]
        message_outil = [m for m in messages_second_tour if m.get("role") == "tool"]
        self.assertEqual(len(message_outil), 1)
        charge = json.loads(message_outil[0]["content"])
        self.assertTrue(charge["ok"])
        self.assertLessEqual(charge["duree_apres_min"], 25)

    def test_le_contexte_est_injecte_des_le_premier_appel(self):
        """« Je fais quoi aujourd'hui ? » ne doit pas trouver un modèle qui ne sait rien."""
        _, llm = self.repondre(
            "Je fais quoi aujourd'hui ?",
            [{"role": "assistant", "content": "Haut du corps.", "tool_calls": []}],
        )

        systeme = llm.appels_recus[0]["messages"][0]
        self.assertEqual(systeme["role"], "system")
        self.assertIn("Développé incliné haltères", systeme["content"])
        self.assertIn("2026-09-16", systeme["content"])


class TestBoucleOutils(_BaseOrchestration):
    def test_enchainement_de_plusieurs_actions(self):
        resultat, _ = self.repondre(
            "J'ai fait ma séance : développé incliné 24 kg 4x8, facile. C'est fini.",
            [
                {"role": "assistant", "content": "",
                 "tool_calls": [_appel("enregistrer_performance", {
                     "nom": "développé incliné", "series": 4, "repetitions": 8,
                     "charge_kg": 24, "difficulte": "facile"})]},
                {"role": "assistant", "content": "",
                 "tool_calls": [_appel("terminer_seance", {}, "call_2")]},
                {"role": "assistant", "content": "C'est enregistré.", "tool_calls": []},
            ],
        )

        self.assertEqual([a["nom"] for a in resultat["actions"]],
                         ["enregistrer_performance", "terminer_seance"])
        self.assertEqual(self.db.query(models.HistoriqueSeance).count(), 1)

    def test_plusieurs_outils_dans_un_meme_tour(self):
        resultat, _ = self.repondre(
            "Où j'en suis ?",
            [
                {"role": "assistant", "content": "", "tool_calls": [
                    _appel("get_profil", {}, "a"),
                    _appel("get_seance_du_jour", {"generer": False}, "b"),
                ]},
                {"role": "assistant", "content": "Voilà où tu en es.", "tool_calls": []},
            ],
        )

        self.assertEqual([a["nom"] for a in resultat["actions"]], ["get_profil", "get_seance_du_jour"])

    def test_arguments_illisibles_ne_cassent_pas_la_conversation(self):
        """Un JSON d'arguments malformé doit se comporter comme un utilisateur trop vague :
        l'action demande une clarification, la conversation continue."""
        resultat, _ = self.repondre(
            "J'ai fait du développé incliné.",
            [
                {"role": "assistant", "content": "", "tool_calls": [
                    {"id": "x", "type": "function",
                     "function": {"name": "enregistrer_performance", "arguments": "{ceci n'est pas du json"}},
                ]},
                {"role": "assistant", "content": "Combien de séries et de reps ?", "tool_calls": []},
            ],
        )

        self.assertFalse(resultat["actions"][0]["resultat"]["ok"])
        self.assertEqual(self.db.query(models.SerieLoggee).count(), 0)
        self.assertEqual(resultat["reponse"], "Combien de séries et de reps ?")

    def test_boucle_bornee(self):
        """Un modèle qui n'arrête jamais d'appeler des outils ne doit pas boucler sans fin."""
        reponses = [
            {"role": "assistant", "content": "", "tool_calls": [_appel("get_profil", {})]}
            for _ in range(coach.MAX_TOURS + 5)
        ]

        resultat, llm = self.repondre("Bonjour ?", reponses)

        self.assertEqual(len(llm.appels_recus), coach.MAX_TOURS)
        self.assertTrue(resultat["reponse"], "une réponse factuelle est produite malgré tout")

    def test_actions_sans_conclusion_produisent_un_resume_factuel(self):
        """Pas de phrase de coach fabriquée à la place du modèle : on dit ce qui a été fait."""
        resultat, _ = self.repondre(
            "Où j'en suis ?",
            [
                {"role": "assistant", "content": "", "tool_calls": [_appel("get_profil", {})]},
                {"role": "assistant", "content": "", "tool_calls": []},
            ],
        )

        self.assertIn("get_profil", resultat["reponse"])


class TestConversationPersistee(_BaseOrchestration):
    def test_message_et_reponse_enregistres(self):
        self.repondre("Je fais quoi aujourd'hui ?",
                      [{"role": "assistant", "content": "Haut du corps, 50 minutes.", "tool_calls": []}])

        messages = self.db.query(models.MessageConversation).order_by(models.MessageConversation.id).all()
        self.assertEqual([m.role for m in messages], ["utilisateur", "coach"])
        self.assertEqual(messages[1].contenu, "Haut du corps, 50 minutes.")

    def test_actions_tracees_sur_le_message_du_coach(self):
        """Permet de vérifier après coup qu'un « c'est enregistré » correspond à une écriture."""
        self.repondre(
            "24 kg, 4x8, facile.",
            [
                {"role": "assistant", "content": "", "tool_calls": [_appel("enregistrer_performance", {
                    "nom": "développé incliné", "series": 4, "repetitions": 8, "charge_kg": 24})]},
                {"role": "assistant", "content": "Enregistré.", "tool_calls": []},
            ],
        )

        message_coach = self.db.query(models.MessageConversation).filter_by(role="coach").one()
        self.assertEqual([a["nom"] for a in message_coach.actions], ["enregistrer_performance"])

    def test_le_fil_precedent_est_rejoue_comme_contexte_de_dialogue(self):
        self.repondre("Salut", [{"role": "assistant", "content": "Prêt.", "tool_calls": []}])

        _, llm = self.repondre("Et aujourd'hui ?",
                               [{"role": "assistant", "content": "Haut du corps.", "tool_calls": []}])

        roles = [m["role"] for m in llm.appels_recus[0]["messages"]]
        self.assertEqual(roles, ["system", "user", "assistant", "user"])

    def test_le_coach_reste_juste_sans_historique_de_conversation(self):
        """Section 24 : le système doit fonctionner même si le fil n'est pas chargé."""
        self.repondre("Salut", [{"role": "assistant", "content": "Prêt.", "tool_calls": []}])
        self.db.query(models.MessageConversation).delete()
        self.db.commit()

        _, llm = self.repondre("Je fais quoi aujourd'hui ?",
                               [{"role": "assistant", "content": "Haut du corps.", "tool_calls": []}])

        systeme = llm.appels_recus[0]["messages"][0]["content"]
        self.assertIn("Développé incliné haltères", systeme)


class TestContexteConstruit(_BaseOrchestration):
    def test_ouvrir_la_conversation_ne_genere_aucune_seance(self):
        """Lecture seule : le contexte n'a pas d'effet de bord sur les données."""
        self.db.query(models.Seance).delete()
        self.db.commit()

        coach.construire_contexte(self.db, AUJOURDHUI)

        self.assertEqual(self.db.query(models.Seance).count(), 0)

    def test_contexte_renvoye_avec_la_reponse(self):
        resultat, _ = self.repondre("Salut", [{"role": "assistant", "content": "Prêt.", "tool_calls": []}])

        self.assertEqual(resultat["contexte"]["jour"]["statut"], "seance")
        self.assertEqual(resultat["contexte"]["seance_du_jour"]["id"], 1)


if __name__ == "__main__":
    unittest.main()
