"""Tests de la couche d'actions métier du coach (coach_actions.py).

Ce que ces tests protègent, côté produit — c'est-à-dire le parcours réel décrit par la
spécification V0 (section 29) :

- « je fais quoi aujourd'hui ? » renvoie la séance du PROGRAMME, jamais une séance inventée,
  et un jour de match/repos est annoncé comme une décision, pas comme une panne ;
- « j'ai fait 24 kg, 4x8, c'était facile » est enregistré en données structurées réelles, et
  le redire deux fois ne crée pas huit séries ;
- « développé incliné lourd » n'est PAS enregistré : la clarification est demandée ;
- « je n'ai que 25 minutes » produit une séance réellement plus courte, enregistrée ;
- « mon match est finalement vendredi » met à jour le calendrier ET le programme ;
- une douleur exclut la zone des séances suivantes et n'est jamais diagnostiquée ;
- rien d'important ne vit uniquement dans la conversation : purger le fil ne fait rien perdre ;
- aucune action ne réécrit l'historique d'une séance terminée.

Nécessite les dépendances du projet (sqlalchemy, fastapi, pydantic) — voir requirements.txt.
Comme les autres tests d'intégration du dépôt (test_historique.py, test_idempotence_parcours.py…),
ce fichier échoue à l'import si elles ne sont pas installées : limitation d'environnement,
jamais contournée ici.

Lancer avec : python3 -m unittest test_coach_actions -v (depuis backend/)
"""

import unittest
from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import coach_actions
import main as main_module
import models

AUJOURDHUI = date(2026, 9, 16)  # un mercredi
SAMEDI = date(2026, 9, 19)
VENDREDI = date(2026, 9, 18)


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
        calendrier_matchs={"jour_habituel": "Samedi", "exceptions": [], "annulations": []},
        contraintes_temps="60 min", materiel="Salle complète",
        objectifs_v2=[{"theme": "force", "rang": 1, "poids": 0.6}],
        contexte_sportif={"sport": "football", "frequence_hebdo": 2, "poste": "Milieu"},
        disponibilites={
            "lundi": 60, "mardi": None, "mercredi": 60, "jeudi": None,
            "vendredi": 60, "samedi": None, "dimanche": None,
        },
    )
    base.update(overrides)
    return models.Profil(**base)


def _exercices_bibliotheque():
    return [
        models.ExerciceBibliotheque(
            id=1, nom="Développé incliné haltères", groupe_musculaire="pectoraux", type="force",
            materiel_requis="haltères et banc", materiel_requis_liste=["halteres", "banc"],
            pattern_mouvement="poussee_horizontale", groupe_musculaire_principal="pectoraux",
            charge_recommandee="charge_lourde_progressive",
        ),
        models.ExerciceBibliotheque(
            id=2, nom="Tirage vertical", groupe_musculaire="dos", type="force",
            materiel_requis="machine", materiel_requis_liste=["machine"],
            pattern_mouvement="tirage_vertical", groupe_musculaire_principal="dos",
            charge_recommandee="charge_moderee",
        ),
        models.ExerciceBibliotheque(
            id=3, nom="Élévations latérales", groupe_musculaire="épaules", type="force",
            materiel_requis="haltères", materiel_requis_liste=["halteres"],
            pattern_mouvement="elevation_laterale", groupe_musculaire_principal="épaules",
            charge_recommandee="charge_legere",
        ),
        models.ExerciceBibliotheque(
            id=4, nom="Pompes", groupe_musculaire="pectoraux", type="force",
            materiel_requis="aucun", materiel_requis_liste=[],
            pattern_mouvement="poussee_horizontale", groupe_musculaire_principal="pectoraux",
            charge_recommandee="poids_du_corps",
        ),
        models.ExerciceBibliotheque(
            id=5, nom="Gainage planche", groupe_musculaire="abdos", type="technique",
            materiel_requis="aucun", materiel_requis_liste=[],
            pattern_mouvement="gainage", groupe_musculaire_principal="abdos",
            charge_recommandee="poids_du_corps",
        ),
        # Alternative « dos » réalisable avec de simples haltères : sans elle, le scénario
        # « je suis chez moi avec deux haltères » n'aurait aucun remplaçant pour le tirage
        # vertical à la machine, et le test vérifierait le refus au lieu de la substitution.
        models.ExerciceBibliotheque(
            id=6, nom="Rowing haltère unilatéral", groupe_musculaire="dos", type="force",
            materiel_requis="haltères", materiel_requis_liste=["halteres"],
            pattern_mouvement="tirage_horizontal", groupe_musculaire_principal="dos",
            charge_recommandee="charge_moderee",
        ),
    ]


def _seance(**overrides):
    base = dict(
        id=1, date=AUJOURDHUI, nom="Haut du corps", statut="planifiee", type_seance="force",
        duree_prevue=50,
        exercices=[
            {"exercice_id": 1, "series": 4, "repetitions": "8", "charge_indicative": "24 kg"},
            {"exercice_id": 2, "series": 3, "repetitions": "10", "charge_indicative": "60 kg"},
            {"exercice_id": 3, "series": 3, "repetitions": "12", "charge_indicative": "8 kg"},
            {"exercice_id": 5, "series": 3, "repetitions": "45 s", "charge_indicative": None},
        ],
    )
    base.update(overrides)
    return models.Seance(**base)


class _BaseCoach(unittest.TestCase):
    """Base commune : DB en mémoire, Mistral coupé (aucun appel réseau dans les tests).

    Le programme retombe donc sur le programme de secours déterministe — exactement le chemin
    emprunté quand Mistral est indisponible en production.
    """

    def setUp(self):
        self.engine, self.TestSessionLocal = _setup_db_memoire()
        self.db = self.TestSessionLocal()

        self._appel_original = main_module.mistral_client.appeler_mistral_json

        def _mistral_indisponible(prompt, system_prompt=None):
            raise main_module.mistral_client.MistralError("hors ligne (test)")

        main_module.mistral_client.appeler_mistral_json = _mistral_indisponible

    def tearDown(self):
        self.db.close()
        main_module.mistral_client.appeler_mistral_json = self._appel_original

    def executer(self, nom, **arguments):
        return coach_actions.executer(nom, arguments, self.db, AUJOURDHUI)

    def peupler(self, avec_seance=False, avec_programme=False, **profil_kwargs):
        self.db.add(_profil(**profil_kwargs))
        for exercice in _exercices_bibliotheque():
            self.db.add(exercice)
        if avec_seance:
            self.db.add(_seance())
        self.db.commit()
        if avec_programme:
            self.executer("generer_programme")


# ---------------------------------------------------------------------------
# Onboarding -> programme
# ---------------------------------------------------------------------------


class TestOnboardingEtProgramme(_BaseCoach):
    def test_programme_genere_et_reellement_enregistre(self):
        """Le programme ne doit pas être seulement affiché dans le chat : il vit en base."""
        self.peupler()

        resultat = self.executer("generer_programme")

        self.assertTrue(resultat["ok"], resultat)
        self.assertTrue(resultat["enregistre"])
        self.assertEqual(self.db.query(models.Programme).filter_by(statut="actif").count(), 1)

    def test_programme_respecte_les_disponibilites_declarees(self):
        """Structure hebdomadaire déterministe : aucune séance un jour déclaré indisponible."""
        self.peupler()

        gabarit = self.executer("generer_programme")["programme"]["gabarit_hebdomadaire"]

        for jour_indispo in ("Mar", "Jeu", "Sam", "Dim"):
            self.assertIn(
                gabarit.get(jour_indispo, "repos"), (None, "repos"),
                f"{jour_indispo} est indisponible au profil : aucune séance ne doit y être placée",
            )

    def test_generation_idempotente(self):
        self.peupler()
        premier = self.executer("generer_programme")["programme"]
        second = self.executer("generer_programme")["programme"]

        self.assertEqual(second["id"], premier["id"])
        self.assertEqual(self.db.query(models.Programme).count(), 1)

    def test_sans_profil_refus_explicite(self):
        resultat = self.executer("generer_programme")

        self.assertFalse(resultat["ok"])
        self.assertIn("onboarding", resultat["erreur"].lower())


# ---------------------------------------------------------------------------
# « Je fais quoi aujourd'hui ? »
# ---------------------------------------------------------------------------


class TestSeanceDuJour(_BaseCoach):
    def test_renvoie_la_seance_existante_sans_en_generer_une_autre(self):
        self.peupler(avec_seance=True)

        resultat = self.executer("get_seance_du_jour")

        self.assertTrue(resultat["ok"])
        self.assertEqual(resultat["seance"]["seance_id"], 1)
        self.assertEqual(self.db.query(models.Seance).count(), 1)

    def test_les_exercices_sont_nommes(self):
        """Le coach doit pouvoir citer « Développé incliné », pas « exercice #1 »."""
        self.peupler(avec_seance=True)

        exercices = self.executer("get_seance_du_jour")["seance"]["exercices"]

        self.assertEqual(exercices[0]["nom"], "Développé incliné haltères")
        self.assertEqual(exercices[0]["series"], 4)

    def test_jour_de_match_est_une_decision_pas_une_erreur(self):
        """Samedi = match : le moteur refuse de générer, et le refus doit être explicable."""
        self.peupler(avec_programme=True)

        resultat = coach_actions.executer("get_seance_du_jour", {}, self.db, SAMEDI)

        self.assertFalse(resultat["ok"])
        self.assertEqual(resultat["contexte_jour"]["statut"], "match")
        self.assertIn("match", resultat["refus_moteur"].lower())
        self.assertEqual(self.db.query(models.Seance).count(), 0, "aucune séance ne doit être créée")

    def test_lecture_seule_ne_genere_rien(self):
        self.peupler(avec_programme=True)

        resultat = self.executer("get_seance_du_jour", generer=False)

        self.assertIsNone(resultat["seance"])
        self.assertEqual(self.db.query(models.Seance).count(), 0)


# ---------------------------------------------------------------------------
# Enregistrement d'une séance par conversation
# ---------------------------------------------------------------------------


class TestEnregistrementPerformance(_BaseCoach):
    def setUp(self):
        super().setUp()
        self.peupler(avec_seance=True)

    def test_enregistre_une_performance_complete(self):
        resultat = self.executer(
            "enregistrer_performance",
            nom="développé incliné", series=4, repetitions=8, charge_kg=24, difficulte="facile",
        )

        self.assertTrue(resultat["ok"], resultat)
        series = self.db.query(models.SerieLoggee).filter_by(exercice_id=1).all()
        self.assertEqual(len(series), 4)
        self.assertTrue(all(s.poids_kg == 24 and s.repetitions == 8 and s.coche == 1 for s in series))

    def test_difficulte_traduite_en_rpe_par_le_backend(self):
        """Le RPE n'est pas fourni par le LLM : il est dérivé côté serveur du vocabulaire
        contrôlé (facile / comme prévu / dur), comme pour le logging dans l'app."""
        self.executer(
            "enregistrer_performance",
            nom="développé incliné", series=4, repetitions=8, charge_kg=24, difficulte="facile",
        )

        series = self.db.query(models.SerieLoggee).filter_by(exercice_id=1).all()
        self.assertTrue(all(s.rpe_approx == main_module.DIFFICULTE_RPE_APPROX["facile"] for s in series))

    def test_le_prevu_est_rattache_pour_comparer_realise_vs_prevu(self):
        self.executer(
            "enregistrer_performance", nom="développé incliné", series=4, repetitions=8, charge_kg=24
        )

        serie = self.db.query(models.SerieLoggee).filter_by(exercice_id=1).first()
        self.assertEqual(serie.reps_prevues, 8)
        self.assertEqual(serie.charge_prevue_kg, 24.0)

    def test_double_appel_identique_ne_duplique_pas(self):
        """« J'ai fait ma séance » renvoyé deux fois (retry réseau, reformulation) ne doit
        jamais produire huit séries."""
        args = dict(nom="développé incliné", series=4, repetitions=8, charge_kg=24, difficulte="facile")
        premier = self.executer("enregistrer_performance", **args)
        second = self.executer("enregistrer_performance", **args)

        self.assertTrue(premier["ok"])
        self.assertTrue(second["ok"])
        self.assertTrue(second["deja_enregistre"])
        self.assertEqual(self.db.query(models.SerieLoggee).filter_by(exercice_id=1).count(), 4)

    def test_correction_remplace_au_lieu_de_cumuler(self):
        self.executer("enregistrer_performance", nom="développé incliné", series=4, repetitions=8, charge_kg=24)
        resultat = self.executer(
            "enregistrer_performance", nom="développé incliné", series=5, repetitions=8, charge_kg=24
        )

        self.assertTrue(resultat["corrige"])
        self.assertEqual(self.db.query(models.SerieLoggee).filter_by(exercice_id=1).count(), 5)

    def test_information_insuffisante_refusee(self):
        """« J'ai fait du développé incliné lourd » ne doit RIEN enregistrer (section 9)."""
        resultat = self.executer("enregistrer_performance", nom="développé incliné")

        self.assertFalse(resultat["ok"])
        self.assertIn("clarification_requise", resultat)
        self.assertEqual(self.db.query(models.SerieLoggee).count(), 0)

    def test_reps_seules_insuffisantes(self):
        resultat = self.executer("enregistrer_performance", nom="développé incliné", repetitions=8)

        self.assertFalse(resultat["ok"])
        self.assertEqual(self.db.query(models.SerieLoggee).count(), 0)

    def test_charge_optionnelle_pour_le_poids_du_corps(self):
        resultat = self.executer("enregistrer_performance", nom="pompes", series=3, repetitions=15)

        self.assertTrue(resultat["ok"], resultat)
        self.assertIsNone(resultat["charge_kg"])

    def test_exercice_hors_seance_du_jour_quand_meme_enregistre(self):
        """Un exercice fait en plus de ce qui était prévu reste une donnée réelle : on
        l'enregistre, sans réécrire ce qui était prévu."""
        resultat = self.executer("enregistrer_performance", nom="pompes", series=3, repetitions=15)

        self.assertTrue(resultat["ok"])
        seance = self.db.get(models.Seance, 1)
        self.assertEqual(len(seance.exercices), 4, "la liste des exercices PRÉVUS ne change pas")

    def test_sans_seance_du_jour_une_seance_libre_est_creee(self):
        self.db.query(models.Seance).delete()
        self.db.commit()

        resultat = self.executer("enregistrer_performance", nom="pompes", series=3, repetitions=15)

        self.assertTrue(resultat["ok"], resultat)
        seance = self.db.query(models.Seance).one()
        self.assertEqual(seance.exercices, [], "aucun « prévu » n'est inventé pour une séance libre")

    def test_seance_terminee_jamais_modifiee(self):
        """Sécurité : aucune modification destructive de l'historique (section 28)."""
        self.executer("enregistrer_performance", nom="développé incliné", series=4, repetitions=8, charge_kg=24)
        self.executer("terminer_seance")

        resultat = self.executer(
            "enregistrer_performance", nom="tirage vertical", series=3, repetitions=10, charge_kg=60
        )

        self.assertFalse(resultat["ok"])
        self.assertIn("terminée", resultat["erreur"])
        self.assertEqual(self.db.query(models.SerieLoggee).filter_by(exercice_id=2).count(), 0)


class TestResolutionNomExercice(_BaseCoach):
    def setUp(self):
        super().setUp()
        self.peupler()

    def test_nom_partiel_resolu(self):
        resultat = self.executer("chercher_exercice", nom="tirage vertical")

        self.assertTrue(resultat["ok"])
        self.assertEqual(resultat["exercice_id"], 2)

    def test_nom_inconnu_demande_une_precision_au_lieu_de_deviner(self):
        resultat = self.executer("chercher_exercice", nom="squat bulgare")

        self.assertFalse(resultat["ok"])
        self.assertFalse(resultat["trouve"])
        self.assertIn("clarification_requise", resultat)

    def test_nom_vide(self):
        resultat = self.executer("chercher_exercice", nom="")
        self.assertFalse(resultat["ok"])


class TestFinDeSeance(_BaseCoach):
    def setUp(self):
        super().setUp()
        self.peupler(avec_seance=True)
        self.executer(
            "enregistrer_performance",
            nom="développé incliné", series=4, repetitions=8, charge_kg=24, difficulte="facile",
        )

    def test_historique_ecrit_a_partir_des_donnees_reelles(self):
        resultat = self.executer("terminer_seance")

        self.assertTrue(resultat["ok"], resultat)
        historique = self.db.query(models.HistoriqueSeance).one()
        self.assertEqual(historique.seance_id, 1)
        realise = historique.exercices_realises[0]
        self.assertEqual(realise["exercice_id"], 1)
        self.assertEqual(len(realise["series"]), 4)

    def test_rpe_calcule_par_le_backend_pas_par_le_llm(self):
        resultat = self.executer("terminer_seance")

        self.assertEqual(resultat["resume"]["rpe"], main_module.DIFFICULTE_RPE_APPROX["facile"])

    def test_double_appel_idempotent(self):
        premier = self.executer("terminer_seance")
        second = self.executer("terminer_seance")

        self.assertTrue(second["deja_terminee"])
        self.assertEqual(second["xp_gagne"], premier["xp_gagne"])
        self.assertEqual(self.db.query(models.HistoriqueSeance).count(), 1)


# ---------------------------------------------------------------------------
# Adaptations
# ---------------------------------------------------------------------------


class TestAdaptations(_BaseCoach):
    def setUp(self):
        super().setUp()
        self.peupler(avec_seance=True)

    def test_moins_de_temps_raccourcit_reellement_et_enregistre(self):
        """« Je n'ai que 25 minutes » : la séance adaptée doit être persistée, pas seulement
        annoncée dans le chat (section 12)."""
        resultat = self.executer("adapter_seance", motif="duree", minutes_disponibles=25)

        self.assertTrue(resultat["ok"], resultat)
        self.assertLessEqual(resultat["duree_apres_min"], 25)
        self.assertLess(resultat["duree_apres_min"], resultat["duree_avant_min"])

        seance = self.db.get(models.Seance, 1)
        self.assertEqual(seance.duree_prevue, resultat["duree_apres_min"])
        total_series = sum(e["series"] for e in seance.exercices)
        self.assertLess(total_series, 13, "le volume doit avoir réellement baissé en base")

    def test_adaptation_tracee_pour_rester_explicable(self):
        self.executer("adapter_seance", motif="duree", minutes_disponibles=25)

        seance = self.db.get(models.Seance, 1)
        self.assertTrue(seance.decision_adaptation["adaptations_coach"])
        self.assertEqual(seance.decision_adaptation["adaptations_coach"][0]["motif"], "duree")

    def test_duree_sans_minutes_demande_une_precision(self):
        resultat = self.executer("adapter_seance", motif="duree")

        self.assertFalse(resultat["ok"])
        self.assertIn("clarification_requise", resultat)

    def test_fatigue_baisse_le_volume_sans_toucher_aux_charges(self):
        charges_avant = [e.get("charge_indicative") for e in self.db.get(models.Seance, 1).exercices]

        resultat = self.executer("signaler_fatigue", details="complètement rincé")

        self.assertTrue(resultat["ok"])
        self.assertTrue(resultat["adaptation"]["ok"])
        seance = self.db.get(models.Seance, 1)
        self.assertEqual([e.get("charge_indicative") for e in seance.exercices], charges_avant)
        self.assertEqual(sum(e["series"] for e in seance.exercices), 13 - 4)

    def test_fatigue_enregistree_comme_contexte(self):
        self.executer("signaler_fatigue", details="rincé")

        contraintes = self.executer("get_contexte_signale")["contraintes"]
        self.assertTrue(any(c["type"] == "fatigue" for c in contraintes))

    def test_materiel_reduit_remplace_les_exercices_impossibles(self):
        """« Je suis chez moi, j'ai juste deux haltères » : le tirage vertical (machine) doit
        être remplacé par un exercice réalisable, en gardant le même objectif."""
        resultat = self.executer("adapter_seance", motif="materiel", materiel="Haltères")

        self.assertTrue(resultat["ok"], resultat)
        seance = self.db.get(models.Seance, 1)
        ids = [e["exercice_id"] for e in seance.exercices]
        self.assertNotIn(2, ids, "le tirage vertical à la machine n'est plus réalisable")
        self.assertIn(6, ids, "il est remplacé par un exercice de dos faisable aux haltères")
        self.assertEqual(len(ids), 4, "on remplace, on ne supprime pas")

    def test_materiel_suffisant_ne_change_rien(self):
        resultat = self.executer("adapter_seance", motif="materiel", materiel="Salle complète")

        self.assertTrue(resultat["ok"])
        self.assertFalse(resultat["enregistre"])
        self.assertEqual([e["exercice_id"] for e in self.db.get(models.Seance, 1).exercices], [1, 2, 3, 5])

    def test_motif_inconnu_refuse(self):
        resultat = self.executer("adapter_seance", motif="humeur")
        self.assertFalse(resultat["ok"])

    def test_seance_terminee_non_adaptable(self):
        seance = self.db.get(models.Seance, 1)
        seance.statut = "terminee"
        self.db.commit()

        resultat = self.executer("adapter_seance", motif="duree", minutes_disponibles=25)

        self.assertFalse(resultat["ok"])
        self.assertIn("terminée", resultat["erreur"])


class TestRemplacementExercice(_BaseCoach):
    def setUp(self):
        super().setUp()
        self.peupler(avec_seance=True)

    def test_alternatives_proposees_sans_rien_appliquer(self):
        """« Je ne peux pas faire le développé incliné » : on propose, on n'impose pas."""
        resultat = self.executer("proposer_alternatives", nom="développé incliné")

        self.assertTrue(resultat["ok"], resultat)
        self.assertLessEqual(len(resultat["alternatives"]), coach_actions.MAX_ALTERNATIVES_PROPOSEES)
        self.assertEqual([e["exercice_id"] for e in self.db.get(models.Seance, 1).exercices], [1, 2, 3, 5])

    def test_alternative_partage_le_meme_objectif(self):
        alternatives = self.executer("proposer_alternatives", nom="développé incliné")["alternatives"]

        self.assertTrue(alternatives, "les pompes partagent le pattern de poussée horizontale")
        self.assertEqual(alternatives[0]["exercice_id"], 4)

    def test_remplacement_applique_conserve_les_series_deja_faites(self):
        self.executer("enregistrer_performance", nom="développé incliné", series=2, repetitions=8, charge_kg=24)

        resultat = self.executer("remplacer_exercice", nom_actuel="développé incliné", nom_nouveau="pompes")

        self.assertTrue(resultat["ok"], resultat)
        self.assertEqual(resultat["series_deja_realisees"], 2)
        self.assertEqual(
            self.db.query(models.SerieLoggee).filter_by(exercice_id=1).count(), 2,
            "les séries déjà réalisées ne sont jamais effacées",
        )


# ---------------------------------------------------------------------------
# Douleur (cas de sécurité)
# ---------------------------------------------------------------------------


class TestDouleur(_BaseCoach):
    def setUp(self):
        super().setUp()
        self.peupler(avec_seance=True)

    def test_zone_enregistree_et_bornee_dans_le_temps(self):
        resultat = self.executer("signaler_douleur", zone="épaules", details="gêne au développé")

        self.assertTrue(resultat["ok"], resultat)
        signal = self.db.query(models.ContexteSignale).filter_by(type="douleur").one()
        self.assertEqual(signal.valeur, "épaules")
        self.assertEqual(signal.date_fin, AUJOURDHUI + timedelta(days=main_module.JOURS_VALIDITE_ZONE_SENSIBLE))

    def test_details_conserves_tels_quels_sans_diagnostic(self):
        self.executer("signaler_douleur", zone="épaules", details="ça tire quand je monte le bras")

        signal = self.db.query(models.ContexteSignale).one()
        self.assertEqual(signal.details, "ça tire quand je monte le bras")
        self.assertIn("diagnostic", self.executer("signaler_douleur", zone="épaules")["consigne_securite"])

    def test_exercices_concernes_identifies_pour_arreter_tout_de_suite(self):
        resultat = self.executer("signaler_douleur", zone="épaules")

        noms = [e["nom"] for e in resultat["exercices_concernes_aujourdhui"]]
        self.assertIn("Élévations latérales", noms)

    def test_douleur_persistante_oriente_vers_un_professionnel(self):
        resultat = self.executer("signaler_douleur", zone="dos", persistante=True)

        self.assertTrue(resultat["orienter_vers_professionnel"])

    def test_zone_invalide_demande_une_precision(self):
        resultat = self.executer("signaler_douleur", zone="genou gauche")

        self.assertFalse(resultat["ok"])
        self.assertIn("zones_possibles", resultat)
        self.assertEqual(self.db.query(models.ContexteSignale).count(), 0)

    def test_zone_exclue_des_seances_suivantes(self):
        """La douleur doit atteindre le moteur : elle est inscrite là où le garde-fou la lit."""
        self.executer("enregistrer_performance", nom="développé incliné", series=4, repetitions=8, charge_kg=24)
        self.executer("terminer_seance")

        self.executer("signaler_douleur", zone="épaules")

        historique = self.db.query(models.HistoriqueSeance).one()
        self.assertEqual(historique.zone_sensible_signalee, "épaules")
        contexte = main_module._construire_contexte_historique(self.db, AUJOURDHUI)
        self.assertIn("épaules", contexte["zones_sensibles_recentes"])


# ---------------------------------------------------------------------------
# Changements de cadre : match, disponibilités
# ---------------------------------------------------------------------------


class TestChangementDeCadre(_BaseCoach):
    def setUp(self):
        super().setUp()
        self.peupler(avec_programme=True)

    def test_match_deplace_met_a_jour_le_calendrier_et_le_programme(self):
        """« Mon match est finalement vendredi au lieu de samedi » : le calendrier change ET
        la semaine est réévaluée par le moteur, pas seulement annoncée."""
        resultat = self.executer(
            "deplacer_match", nouvelle_date=VENDREDI.isoformat(), date_annulee=SAMEDI.isoformat()
        )

        self.assertTrue(resultat["ok"], resultat)
        self.assertTrue(resultat["programme_recalcule"])

        calendrier = resultat["calendrier_matchs"]
        self.assertIn(SAMEDI.isoformat(), calendrier["annulations"])
        self.assertTrue(any(e["date"] == VENDREDI.isoformat() for e in calendrier["exceptions"]))

    def test_le_moteur_voit_le_vendredi_comme_jour_de_match(self):
        self.executer("deplacer_match", nouvelle_date=VENDREDI.isoformat(), date_annulee=SAMEDI.isoformat())

        contexte_vendredi = coach_actions.executer("get_contexte_jour", {}, self.db, VENDREDI)
        contexte_samedi = coach_actions.executer("get_contexte_jour", {}, self.db, SAMEDI)

        self.assertEqual(contexte_vendredi["contexte_jour"]["statut"], "match")
        self.assertNotEqual(contexte_samedi["contexte_jour"]["statut"], "match")

    def test_date_invalide_refusee(self):
        resultat = self.executer("deplacer_match", nouvelle_date="vendredi prochain")

        self.assertFalse(resultat["ok"])
        self.assertIn("clarification_requise", resultat)

    def test_disponibilites_mises_a_jour_reconstruisent_le_programme(self):
        """« Je ne peux pas m'entraîner vendredi » : le reste de la semaine est réorganisé."""
        resultat = self.executer("mettre_a_jour_disponibilites", disponibilites={"vendredi": None, "jeudi": 60})

        self.assertTrue(resultat["ok"], resultat)
        self.assertTrue(resultat["programme_recalcule"])
        self.assertIsNone(resultat["disponibilites"]["vendredi"])
        self.assertEqual(resultat["disponibilites"]["jeudi"], 60)
        self.assertEqual(resultat["disponibilites"]["lundi"], 60, "les jours non cités ne changent pas")

    def test_jour_inconnu_refuse(self):
        resultat = self.executer("mettre_a_jour_disponibilites", disponibilites={"lundu": 60})

        self.assertFalse(resultat["ok"])
        self.assertIn("jours_attendus", resultat)

    def test_materiel_mis_a_jour_durablement(self):
        resultat = self.executer("mettre_a_jour_materiel", materiel="Haltères")

        self.assertTrue(resultat["ok"], resultat)
        self.assertEqual(resultat["profil"]["materiel"], "Haltères")


# ---------------------------------------------------------------------------
# Progression : données réelles uniquement
# ---------------------------------------------------------------------------


class TestProgression(_BaseCoach):
    def setUp(self):
        super().setUp()
        self.peupler()

    def _seance_terminee(self, jour, charge, reps=8, series=4):
        seance = models.Seance(
            date=jour, nom="Haut du corps", statut="terminee", type_seance="force",
            exercices=[{"exercice_id": 1, "series": series, "repetitions": str(reps),
                        "charge_indicative": f"{charge} kg"}],
        )
        self.db.add(seance)
        self.db.commit()
        for numero in range(1, series + 1):
            self.db.add(models.SerieLoggee(
                seance_id=seance.id, exercice_id=1, numero_serie=numero,
                poids_kg=charge, repetitions=reps, coche=1, difficulte="facile", rpe_approx=5,
            ))
        self.db.commit()

    def test_progression_lue_dans_les_donnees_reelles(self):
        self._seance_terminee(AUJOURDHUI - timedelta(days=7), 20)
        self._seance_terminee(AUJOURDHUI - timedelta(days=3), 24)

        resultat = self.executer("get_progression_exercice", nom="développé incliné")

        self.assertTrue(resultat["ok"], resultat)
        self.assertTrue(resultat["assez_de_donnees"])
        self.assertEqual([s["charge_max_kg"] for s in resultat["seances"]], [20.0, 24.0])

    def test_sans_donnees_le_manque_est_dit_pas_comble(self):
        """Section 17 : ne jamais générer de statistiques fictives."""
        resultat = self.executer("get_progression_exercice", nom="développé incliné")

        self.assertTrue(resultat["ok"])
        self.assertFalse(resultat["assez_de_donnees"])
        self.assertEqual(resultat["seances"], [])

    def test_seance_non_terminee_exclue(self):
        """Une séance abandonnée en cours de route n'est pas une performance de référence."""
        self._seance_terminee(AUJOURDHUI - timedelta(days=7), 20)
        seance = models.Seance(date=AUJOURDHUI, nom="En cours", statut="planifiee", exercices=[])
        self.db.add(seance)
        self.db.commit()
        self.db.add(models.SerieLoggee(
            seance_id=seance.id, exercice_id=1, numero_serie=1, poids_kg=100, repetitions=8, coche=1
        ))
        self.db.commit()

        resultat = self.executer("get_progression_exercice", nom="développé incliné")

        self.assertEqual(resultat["nb_seances"], 1)
        self.assertEqual(resultat["seances"][0]["charge_max_kg"], 20.0)


# ---------------------------------------------------------------------------
# Mémoire structurée : la conversation n'est jamais la source de vérité
# ---------------------------------------------------------------------------


class TestMemoireStructuree(_BaseCoach):
    def test_purger_la_conversation_ne_fait_rien_perdre(self):
        """Section 24 : le système doit fonctionner même sans l'historique conversationnel."""
        self.peupler(avec_seance=True)
        self.executer(
            "enregistrer_performance",
            nom="développé incliné", series=4, repetitions=8, charge_kg=24, difficulte="facile",
        )
        self.executer("terminer_seance")
        self.executer("signaler_douleur", zone="épaules")

        self.db.query(models.MessageConversation).delete()
        self.db.commit()

        self.assertEqual(self.db.query(models.HistoriqueSeance).count(), 1)
        self.assertEqual(self.db.query(models.SerieLoggee).count(), 4)
        self.assertEqual(self.db.query(models.ContexteSignale).count(), 1)

        progression = self.executer("get_progression_exercice", nom="développé incliné")
        self.assertEqual(progression["nb_seances"], 1)


class TestRegistreActions(_BaseCoach):
    def test_action_inconnue_refusee_proprement(self):
        resultat = self.executer("supprimer_tout")

        self.assertFalse(resultat["ok"])
        self.assertIn("inconnue", resultat["erreur"])

    def test_arguments_invalides_ne_font_pas_tomber_la_conversation(self):
        self.peupler()

        resultat = coach_actions.executer("get_historique", {"limite": "beaucoup"}, self.db, AUJOURDHUI)

        self.assertFalse(resultat["ok"])
        self.assertIn("erreur", resultat)

    def test_arguments_non_dict_refuses(self):
        resultat = coach_actions.executer("get_profil", ["oups"], self.db, AUJOURDHUI)

        self.assertFalse(resultat["ok"])


if __name__ == "__main__":
    unittest.main()
