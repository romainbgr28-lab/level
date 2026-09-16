"""Tests du contexte déterministe du jour (contexte_jour.py) et de la phase calendaire
(regles_seance.calculer_phase_calendaire), sans base ni FastAPI."""

import unittest
from datetime import date, timedelta

import contexte_jour
import regles_seance

# 2026-09-14 est un lundi : toutes les dates des tests s'y réfèrent.
LUNDI = date(2026, 9, 14)
JOURS = {nom: LUNDI + timedelta(days=i) for i, nom in enumerate(
    ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
)}

DISPO = {"lundi": 60, "mardi": None, "mercredi": 60, "jeudi": None,
         "vendredi": 60, "samedi": None, "dimanche": None}

GABARIT = {"Lun": "force", "Mer": "esthétique", "Ven": "explosivité_vitesse"}

PROGRAMME = {
    "gabarit_hebdomadaire": GABARIT,
    "phases": [{"nom": "Fondations", "description": "Base", "semaine_debut": 1, "semaine_fin": 4}],
    "duree_semaines": 8,
    "date_debut": LUNDI,
}


def profil(jour_match=None):
    return {"disponibilites": DISPO, "calendrier_matchs": {"jour_habituel": jour_match, "exceptions": []}}


class TestPhaseCalendaire(unittest.TestCase):
    def test_jour_de_match_detecte(self):
        """Le match a lieu aujourd'hui : _dates_matchs_proches renvoie aujourd'hui comme
        prochain match (écart 0), ce qui doit produire "jour_match" et non "phase_normale"."""
        phase, intensite = regles_seance.calculer_phase_calendaire(LUNDI, LUNDI, None)
        self.assertEqual(phase, "jour_match")
        self.assertEqual(intensite, "repos_match")

    def test_lendemain_de_match(self):
        """Le dernier match est strictement antérieur à aujourd'hui : le lendemain correspond
        donc à un écart de 1 jour (et non 0, qui rendait la branche inatteignable)."""
        phase, intensite = regles_seance.calculer_phase_calendaire(LUNDI, None, LUNDI - timedelta(days=1))
        self.assertEqual(phase, "lendemain_match")
        self.assertEqual(intensite, "récupération")

    def test_veille_et_approche_inchangees(self):
        self.assertEqual(regles_seance.calculer_phase_calendaire(LUNDI, LUNDI + timedelta(days=1), None)[0], "veille_match")
        self.assertEqual(regles_seance.calculer_phase_calendaire(LUNDI, LUNDI + timedelta(days=2), None)[0], "approche_match")

    def test_phase_normale_sans_match_proche(self):
        self.assertEqual(regles_seance.calculer_phase_calendaire(LUNDI, LUNDI + timedelta(days=5), None)[0], "phase_normale")

    def test_jour_de_match_impose_decharge(self):
        self.assertEqual(regles_seance._suggerer_type_seance("jour_match", [], None, "force"), "décharge")

    def test_lendemain_match_impose_decharge_malgre_gabarit(self):
        self.assertEqual(regles_seance._suggerer_type_seance("lendemain_match", [], None, "force"), "décharge")


class TestContexteJour(unittest.TestCase):
    def test_sans_profil(self):
        ctx = contexte_jour.construire_contexte_jour(None, None, LUNDI)
        self.assertEqual(ctx["statut"], "aucun_profil")
        self.assertEqual(ctx["semaine"], [])

    def test_sans_programme(self):
        ctx = contexte_jour.construire_contexte_jour(profil(), None, LUNDI)
        self.assertEqual(ctx["statut"], "aucun_programme")

    def test_jour_de_seance(self):
        ctx = contexte_jour.construire_contexte_jour(profil(), PROGRAMME, JOURS["mercredi"])
        self.assertEqual(ctx["statut"], "seance")
        self.assertEqual(ctx["type_seance_prevu"], "esthétique")
        self.assertEqual(ctx["semaine_programme"], 1)
        self.assertEqual(ctx["phase_nom"], "Fondations")

    def test_jour_indisponible(self):
        """Mardi n'est pas déclaré disponible : ce n'est pas un "repos décidé", c'est une
        contrainte du profil — l'écran doit pouvoir le dire tel quel."""
        ctx = contexte_jour.construire_contexte_jour(profil(), PROGRAMME, JOURS["mardi"])
        self.assertEqual(ctx["statut"], "indisponible")
        self.assertIsNone(ctx["type_seance_prevu"])

    def test_jour_de_match_prime_sur_le_gabarit(self):
        ctx = contexte_jour.construire_contexte_jour(profil("Lundi"), PROGRAMME, JOURS["lundi"])
        self.assertEqual(ctx["statut"], "match")
        self.assertEqual(ctx["phase_calendaire"], "jour_match")
        self.assertIsNone(ctx["type_seance_prevu"])

    def test_match_par_exception_de_calendrier(self):
        p = profil()
        p["calendrier_matchs"]["exceptions"] = [{"date": JOURS["mercredi"].isoformat()}]
        ctx = contexte_jour.construire_contexte_jour(p, PROGRAMME, JOURS["mercredi"])
        self.assertEqual(ctx["statut"], "match")

    def test_repos_programme(self):
        gabarit_repos = dict(GABARIT, Lun="repos")
        prog = dict(PROGRAMME, gabarit_hebdomadaire=gabarit_repos)
        ctx = contexte_jour.construire_contexte_jour(profil(), prog, JOURS["lundi"])
        self.assertEqual(ctx["statut"], "repos")

    def test_prochaine_seance(self):
        ctx = contexte_jour.construire_contexte_jour(profil(), PROGRAMME, JOURS["lundi"])
        self.assertEqual(ctx["prochaine_seance"]["jour_abbrev"], "Mer")
        self.assertEqual(ctx["prochaine_seance"]["type_seance_prevu"], "esthétique")
        self.assertEqual(ctx["prochaine_seance"]["date"], JOURS["mercredi"])

    def test_prochaine_seance_saute_le_jour_de_match(self):
        ctx = contexte_jour.construire_contexte_jour(profil("Mercredi"), PROGRAMME, JOURS["lundi"])
        self.assertEqual(ctx["prochaine_seance"]["jour_abbrev"], "Ven")

    def test_semaine_complete_sept_jours(self):
        ctx = contexte_jour.construire_contexte_jour(profil("Samedi"), PROGRAMME, JOURS["mercredi"])
        self.assertEqual(len(ctx["semaine"]), 7)
        self.assertEqual([j["jour_abbrev"] for j in ctx["semaine"]],
                         ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"])
        par_jour = {j["jour_abbrev"]: j for j in ctx["semaine"]}
        self.assertEqual(par_jour["Sam"]["statut"], "match")
        self.assertEqual(par_jour["Mar"]["statut"], "indisponible")
        self.assertEqual(par_jour["Lun"]["statut"], "seance")
        self.assertTrue(par_jour["Mer"]["est_aujourdhui"])
        self.assertTrue(par_jour["Lun"]["est_passe"])
        self.assertFalse(par_jour["Ven"]["est_passe"])

    def test_seance_du_jour_reportee(self):
        ctx = contexte_jour.construire_contexte_jour(
            profil(), PROGRAMME, JOURS["lundi"], seance_du_jour={"id": 7, "statut": "terminee", "nom": "Force A"}
        )
        self.assertEqual((ctx["seance_id"], ctx["seance_statut"], ctx["seance_nom"]), (7, "terminee", "Force A"))

    def test_semaine_programme_plafonnee(self):
        ctx = contexte_jour.construire_contexte_jour(profil(), PROGRAMME, LUNDI + timedelta(days=7 * 20))
        self.assertEqual(ctx["semaine_programme"], 8)


class TestContratSchema(unittest.TestCase):
    """Le contrat entre construire_contexte_jour() et schemas.ContexteJourOut est vérifié par
    lecture de l'AST de schemas.py : pydantic n'est pas installable dans cet environnement, mais
    une divergence de nom de champ (le mode d'échec réel — un champ renommé d'un seul côté
    disparaît silencieusement de la réponse) reste détectable ici."""

    @staticmethod
    def _champs_modele(nom_classe):
        import ast
        arbre = ast.parse(open("schemas.py", encoding="utf-8").read())
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.ClassDef) and noeud.name == nom_classe:
                return {c.target.id for c in noeud.body if isinstance(c, ast.AnnAssign)}
        raise AssertionError(f"classe {nom_classe} introuvable dans schemas.py")

    def test_champs_contexte_jour(self):
        ctx = contexte_jour.construire_contexte_jour(profil("Samedi"), PROGRAMME, JOURS["mercredi"])
        self.assertEqual(set(ctx.keys()), self._champs_modele("ContexteJourOut"))

    def test_champs_jour_semaine(self):
        ctx = contexte_jour.construire_contexte_jour(profil(), PROGRAMME, JOURS["mercredi"])
        self.assertEqual(set(ctx["semaine"][0].keys()), self._champs_modele("JourSemaineOut"))

    def test_champs_prochaine_seance(self):
        ctx = contexte_jour.construire_contexte_jour(profil(), PROGRAMME, JOURS["lundi"])
        self.assertEqual(set(ctx["prochaine_seance"].keys()), self._champs_modele("ProchaineSeanceOut"))

    def test_statuts_connus(self):
        """Tout statut produit appartient à STATUTS_JOUR (miroir de ApiStatutJour côté frontend)."""
        for jour_match in (None, "Samedi"):
            for jour in JOURS.values():
                ctx = contexte_jour.construire_contexte_jour(profil(jour_match), PROGRAMME, jour)
                self.assertIn(ctx["statut"], contexte_jour.STATUTS_JOUR)
                for j in ctx["semaine"]:
                    self.assertIn(j["statut"], contexte_jour.STATUTS_JOUR)


if __name__ == "__main__":
    unittest.main()
