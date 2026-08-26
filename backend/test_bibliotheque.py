"""Tests de cohérence des données de la bibliothèque d'exercices (enrichissement à 71
exercices) : pas de logique moteur ici, uniquement la validité des données sources
(JSON + annotations) et leur compatibilité avec substitution.py, sans modifier ce dernier.

Lancer avec `python3 -m unittest test_bibliotheque -v` depuis backend/, sans rien installer.
"""

import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from connaissances import get_exercices_bibliotheque_extension, get_exercices_musculation_base
from data.annotations_substitution import ANNOTATIONS
from substitution import ExerciceDict, exercice_vers_dict, trouver_alternatives

_DATA_DIR = Path(__file__).parent / "data"

# Mêmes ensembles fermés que ceux utilisés dans ANNOTATIONS aujourd'hui (50 exercices
# existants + 21 ajoutés) — pas une contrainte du moteur (pattern_mouvement/
# groupe_musculaire_principal restent des chaînes libres côté substitution.py), mais un
# garde-fou anti-faute-de-frappe pour ce fichier de données.
PATTERNS_CONNUS = {
    "squat", "hinge", "fente", "poussee_horizontale", "poussee_verticale",
    "tirage_horizontal", "tirage_vertical", "sprint", "saut_vertical", "saut_horizontal",
    "deplacement_agilite", "lancer_explosif", "endurance_intermittente", "gainage",
    "stabilite_hanche", "rotation", "isolation_bras", "isolation_epaule", "isolation_mollet",
    "technique_ballon", "mobilite", "echauffement_general",
}
GROUPES_MUSCULAIRES_CONNUS = {
    "jambes", "pectoraux", "dos", "chaine_posterieure", "fessiers", "epaules",
    "abdominaux", "obliques", "ischio_jambiers", "adducteurs", "stabilisateurs",
    "biceps", "triceps", "mollets", "hanches", "coordination", "corps_entier",
}
MATERIEL_CONNU = {
    "barre", "halteres", "banc", "barre_fixe", "machine", "mini_haies",
    "medicine_ball", "plots", "echelle_rythme", "ballon",
}
NIVEAUX_CONNUS = {"debutant", "intermediaire", "avance"}

NOMS_21_NOUVEAUX = {
    "Squat poids du corps (air squat)",
    "Goblet squat",
    "Sumo squat",
    "Front squat",
    "Romanian deadlift (RDL)",
    "RDL unilatéral haltère",
    "Pompes (push-up)",
    "Pompes inclinées (incline push-up)",
    "Développé couché haltères",
    "Développé épaules haltères assis",
    "Pike push-up",
    "Push press",
    "Rowing haltère unilatéral",
    "Rowing inversé (inverted row)",
    "Tractions strictes (pull-up)",
    "Extension mollets unilatérale",
    "Extension mollets unilatérale poids du corps",
    "Adduction de hanche au sol",
    "Saut en longueur (broad jump)",
    "Countermovement jump (CMJ)",
    "Décélération / réception unilatérale contrôlée",
}


def _toutes_les_fiches() -> list[dict]:
    """Reproduit la logique de dédoublonnage de seed.py (base d'abord, puis extension,
    par nom) sans toucher à la base de données."""
    fiches: list[dict] = []
    noms_vus: set[str] = set()
    for fiche in get_exercices_musculation_base():
        if fiche["nom"] in noms_vus:
            continue
        noms_vus.add(fiche["nom"])
        fiches.append(fiche)
    for fiche in get_exercices_bibliotheque_extension():
        if fiche["nom"] in noms_vus:
            continue
        noms_vus.add(fiche["nom"])
        fiches.append(fiche)
    return fiches


def _bibliotheque_exercice_dict() -> list[ExerciceDict]:
    """Construit la bibliothèque complète sous forme d'ExerciceDict (comme le ferait
    exercice_vers_dict() sur les lignes ORM après le seed), pour exercer trouver_alternatives
    sans base de données."""
    bib: list[ExerciceDict] = []
    for i, fiche in enumerate(_toutes_les_fiches(), start=1):
        annotation = ANNOTATIONS.get(fiche["nom"], {})
        faux_orm = SimpleNamespace(
            id=i,
            nom=fiche["nom"],
            type=fiche.get("type", "force"),
            groupe_musculaire=fiche["groupe_musculaire"],
            materiel_requis=fiche.get("materiel_requis"),
            materiel_requis_liste=annotation.get("materiel_requis_liste"),
            pattern_mouvement=annotation.get("pattern_mouvement"),
            groupe_musculaire_principal=annotation.get("groupe_musculaire_principal"),
        )
        bib.append(exercice_vers_dict(faux_orm))
    return bib


class TestCoherenceBibliotheque(unittest.TestCase):
    def test_aucun_doublon_de_nom_dans_les_fichiers_sources(self):
        noms = [f["nom"] for f in get_exercices_musculation_base()] + [
            f["nom"] for f in get_exercices_bibliotheque_extension()
        ]
        doublons = {nom for nom in noms if noms.count(nom) > 1}
        self.assertEqual(doublons, set())

    def test_chargement_complet_71_exercices(self):
        fiches = _toutes_les_fiches()
        self.assertEqual(len(fiches), 71)

    def test_exactement_21_nouvelles_entrees(self):
        noms_existants_avant = {
            "Squat (back squat / squat libre)",
            "Développé couché (bench press)",
            "Rowing buste penché (barbell row)",
            "Soulevé de terre (deadlift)",
        }
        noms_extension = {f["nom"] for f in get_exercices_bibliotheque_extension()}
        nouveaux = noms_extension - noms_existants_avant
        # 46 exercices d'extension existants + 21 nouveaux = 67 ; + les 4 de base = 71.
        self.assertEqual(len(noms_extension), 67)
        self.assertTrue(NOMS_21_NOUVEAUX.issubset(nouveaux))

    def test_chaque_exercice_a_une_annotation(self):
        for fiche in _toutes_les_fiches():
            self.assertIn(fiche["nom"], ANNOTATIONS, f"Annotation manquante pour {fiche['nom']!r}")

    def test_annotations_len_71(self):
        self.assertEqual(len(ANNOTATIONS), 71)

    def test_patterns_valides(self):
        for nom, annotation in ANNOTATIONS.items():
            self.assertIn(annotation["pattern_mouvement"], PATTERNS_CONNUS, nom)

    def test_groupes_musculaires_principaux_valides(self):
        for nom, annotation in ANNOTATIONS.items():
            self.assertIn(annotation["groupe_musculaire_principal"], GROUPES_MUSCULAIRES_CONNUS, nom)

    def test_materiel_reconnu(self):
        for nom, annotation in ANNOTATIONS.items():
            for tag in annotation["materiel_requis_liste"]:
                self.assertIn(tag, MATERIEL_CONNU, f"{nom} -> tag inconnu {tag!r}")

    def test_niveaux_valides_dans_fiches_exercices_json(self):
        with open(_DATA_DIR / "fiches_exercices.json", encoding="utf-8") as f:
            data = json.load(f)
        exercices = data["exercices"]
        self.assertEqual(set(exercices.keys()), NOMS_21_NOUVEAUX)
        for nom, fiche in exercices.items():
            self.assertIn(fiche["niveau"], NIVEAUX_CONNUS, nom)

    def test_fiches_exercices_json_non_charge_dans_annotations(self):
        # Garde-fou architecture : fiches_exercices.json (niveau/fiche_ui/fiche_scientifique)
        # reste un fichier de référence statique, distinct de ANNOTATIONS (pattern/gm/materiel),
        # non fusionné avec elle.
        for annotation in ANNOTATIONS.values():
            self.assertEqual(set(annotation.keys()), {
                "pattern_mouvement", "groupe_musculaire_principal", "materiel_requis_liste",
            })

    def test_pas_de_type_puissance(self):
        types_utilises = {f.get("type") for f in get_exercices_bibliotheque_extension()}
        self.assertNotIn("puissance", types_utilises)

    def test_pas_de_pattern_deceleration(self):
        patterns_utilises = {a["pattern_mouvement"] for a in ANNOTATIONS.values()}
        self.assertNotIn("deceleration", patterns_utilises)

    def test_exercice_17_extension_mollets_unilaterale_poids_du_corps(self):
        noms_extension = {f["nom"] for f in get_exercices_bibliotheque_extension()}
        self.assertIn("Extension mollets unilatérale poids du corps", noms_extension)
        self.assertNotIn("Extension mollets poids du corps", noms_extension)

    def test_push_press_broad_jump_cmj_sont_explosivite(self):
        par_nom = {f["nom"]: f for f in get_exercices_bibliotheque_extension()}
        for nom in ["Push press", "Saut en longueur (broad jump)", "Countermovement jump (CMJ)"]:
            self.assertEqual(par_nom[nom]["type"], "explosivité", nom)

    def test_compatibilite_exercice_vers_dict_pour_les_71(self):
        bib = _bibliotheque_exercice_dict()
        self.assertEqual(len(bib), 71)
        for candidat in bib:
            # Fumée minimale : chaque exercice doit pouvoir participer à trouver_alternatives
            # sans lever d'exception, quel que soit le matériel déclaré.
            trouver_alternatives(candidat, bib, set(), "Salle complète", [])


class TestNouvellesAlternativesPatternsEnrichis(unittest.TestCase):
    """Vérifie, sur la bibliothèque réelle (pas des fixtures), que les patterns identifiés
    comme pauvres en phase d'audit ont désormais de vraies alternatives biomécaniques,
    sans modifier substitution.py."""

    @classmethod
    def setUpClass(cls):
        cls.bib = _bibliotheque_exercice_dict()

    def _par_nom(self, nom: str) -> ExerciceDict:
        return next(e for e in self.bib if e["nom"] == nom)

    def test_squat_a_desormais_des_alternatives_squat(self):
        squat = self._par_nom("Squat (back squat / squat libre)")
        candidats = trouver_alternatives(squat, self.bib, set(), "Salle complète", [])
        alternatives_squat = [
            c for c in candidats if c["exercice"]["pattern_mouvement"] == "squat"
        ]
        self.assertGreaterEqual(len(alternatives_squat), 3)

    def test_squat_a_une_alternative_squat_sans_materiel(self):
        squat = self._par_nom("Squat (back squat / squat libre)")
        candidats = trouver_alternatives(squat, self.bib, set(), "Aucun", [])
        noms = [c["exercice"]["nom"] for c in candidats if c["exercice"]["pattern_mouvement"] == "squat"]
        self.assertIn("Squat poids du corps (air squat)", noms)

    def test_rowing_a_une_alternative_tirage_horizontal(self):
        rowing = self._par_nom("Rowing buste penché (barbell row)")
        candidats = trouver_alternatives(rowing, self.bib, set(), "Salle complète", [])
        alternatives = [c for c in candidats if c["exercice"]["pattern_mouvement"] == "tirage_horizontal"]
        self.assertGreaterEqual(len(alternatives), 2)

    def test_tirage_vertical_a_une_alternative(self):
        tirage = self._par_nom("Tirage vertical (dos)")
        candidats = trouver_alternatives(tirage, self.bib, set(), "Salle complète", [])
        alternatives = [c for c in candidats if c["exercice"]["pattern_mouvement"] == "tirage_vertical"]
        self.assertGreaterEqual(len(alternatives), 1)

    def test_tirage_vertical_toujours_aucune_alternative_sans_barre_fixe(self):
        # Limite matérielle assumée (décision 7) : aucune alternative tirage vertical
        # n'existe encore sans barre fixe -> ne doit pas apparaître à "Aucun"/"Haltères".
        tirage = self._par_nom("Tirage vertical (dos)")
        for materiel in ["Aucun", "Poids du corps", "Haltères"]:
            candidats = trouver_alternatives(tirage, self.bib, set(), materiel, [])
            alternatives = [c for c in candidats if c["exercice"]["pattern_mouvement"] == "tirage_vertical"]
            self.assertEqual(alternatives, [], materiel)

    def test_hip_thrust_a_des_alternatives_hinge_enrichies(self):
        hip_thrust = self._par_nom("Hip thrust (fessiers)")
        candidats = trouver_alternatives(hip_thrust, self.bib, set(), "Salle complète", [])
        alternatives = [c for c in candidats if c["exercice"]["pattern_mouvement"] == "hinge"]
        noms = [c["exercice"]["nom"] for c in alternatives]
        self.assertIn("Romanian deadlift (RDL)", noms)

    def test_developpe_couche_a_une_alternative_sans_materiel(self):
        bench = self._par_nom("Développé couché (bench press)")
        candidats = trouver_alternatives(bench, self.bib, set(), "Poids du corps", [])
        noms = [c["exercice"]["nom"] for c in candidats if c["exercice"]["pattern_mouvement"] == "poussee_horizontale"]
        self.assertIn("Pompes (push-up)", noms)

    def test_type_seul_toujours_insuffisant_push_press_vs_squat_jump(self):
        # Push press et Squat jump partagent type="explosivité" mais aucun autre critère
        # pertinent -> ne doivent jamais s'apparier (règle _est_pertinent non modifiée).
        push_press = self._par_nom("Push press")
        candidats = trouver_alternatives(push_press, self.bib, set(), "Salle complète", [])
        self.assertNotIn("Squat jump", [c["exercice"]["nom"] for c in candidats])


if __name__ == "__main__":
    unittest.main()
