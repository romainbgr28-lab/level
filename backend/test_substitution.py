"""Tests de l'Étape 7C (matching matériel par tags normalisés + garde-fou de pertinence
biomécanique pour le remplacement d'exercice).

Fonctions pures, sans dépendance FastAPI/SQLAlchemy (substitution.py n'en a aucune) :
lancer avec `python3 -m unittest test_substitution -v` depuis backend/, sans rien installer.
"""

import unittest
from types import SimpleNamespace

from data.annotations_substitution import ANNOTATIONS
from substitution import (
    ExerciceDict,
    exercice_vers_dict,
    trouver_alternatives,
)


def ex(
    id: int,
    nom: str,
    type_: str,
    groupe_musculaire: str,
    pattern_mouvement: str | None,
    groupe_musculaire_principal: str | None,
    materiel_requis_liste: list[str] | None,
    materiel_requis: str | None = None,
) -> ExerciceDict:
    return {
        "id": id,
        "nom": nom,
        "type": type_,
        "groupe_musculaire": groupe_musculaire,
        "materiel_requis": materiel_requis,
        "materiel_requis_liste": materiel_requis_liste,
        "pattern_mouvement": pattern_mouvement,
        "groupe_musculaire_principal": groupe_musculaire_principal,
    }


# Fixtures reprenant les valeurs réelles de la bibliothèque (annotations_substitution.py +
# data/bibliotheque_exercices_extension.json), pas des valeurs inventées pour les besoins du
# test — cohérent avec l'exemple concret de l'audit Étape 7C (Hip thrust).
HIP_THRUST = ex(1, "Hip thrust (fessiers)", "force", "fessiers, ischio-jambiers", "hinge", "fessiers", ["banc"])
DEVELOPPE_COUCHE = ex(2, "Développé couché (bench press)", "force", "pectoraux, épaules, triceps", "poussee_horizontale", "pectoraux", ["barre", "halteres"])
DEVELOPPE_EPAULES = ex(3, "Développé épaules (overhead press)", "force", "épaules, triceps", "poussee_verticale", "epaules", ["halteres", "barre"])
NORDIC_HAMSTRING = ex(4, "Nordic hamstring curl", "gainage_prevention", "ischio-jambiers", "hinge", "ischio_jambiers", [])
PONT_FESSIER = ex(5, "Pont fessier (glute bridge)", "gainage_prevention", "fessiers, ischio-jambiers, lombaires", "hinge", "fessiers", [])
SOULEVE_DE_TERRE = ex(6, "Soulevé de terre (deadlift)", "force", "chaîne postérieure complète (dos, fessiers, ischio-jambiers)", "hinge", "chaine_posterieure", ["barre", "halteres"])
FENTE_AVANT = ex(7, "Fente avant (lunge)", "force", "jambes, fessiers, gainage", "fente", "jambes", [])
FENTE_BULGARE = ex(8, "Fente bulgare (pied arrière surélevé)", "force", "jambes, fessiers", "fente", "jambes", ["banc"])


def bibliotheque_par_defaut() -> list[ExerciceDict]:
    return [
        HIP_THRUST,
        DEVELOPPE_COUCHE,
        DEVELOPPE_EPAULES,
        NORDIC_HAMSTRING,
        PONT_FESSIER,
        SOULEVE_DE_TERRE,
        FENTE_AVANT,
        FENTE_BULGARE,
    ]


def noms(candidats: list[dict]) -> list[str]:
    return [c["exercice"]["nom"] for c in candidats]


class TestPertinenceEtMateriel(unittest.TestCase):
    # --- 1. Hip thrust : aucun développé couché / épaules dans les alternatives ---

    def test_1_hip_thrust_exclut_developpes(self):
        candidats = trouver_alternatives(HIP_THRUST, bibliotheque_par_defaut(), set(), "Salle complète", [])
        self.assertNotIn("Développé couché (bench press)", noms(candidats))
        self.assertNotIn("Développé épaules (overhead press)", noms(candidats))

    # --- 2. Hip thrust avec Nordic disponible : retourné si matériel compatible ---

    def test_2_nordic_retourne_si_materiel_compatible(self):
        # Nordic n'a aucun matériel requis (liste vide) : compatible avec toute catégorie,
        # y compris la plus restrictive ("Aucun").
        candidats = trouver_alternatives(HIP_THRUST, bibliotheque_par_defaut(), set(), "Aucun", [])
        self.assertIn("Nordic hamstring curl", noms(candidats))

    # --- 3. Un candidat "type" seul n'est jamais retourné ---

    def test_3_candidat_type_seul_jamais_retourne(self):
        # Fente avant ne partage avec Hip thrust que "type=force" (pattern fente != hinge,
        # groupe jambes != fessiers) : ne doit jamais apparaître.
        candidats = trouver_alternatives(HIP_THRUST, [HIP_THRUST, FENTE_AVANT], set(), "Salle complète", [])
        self.assertEqual(candidats, [])

    # --- 4. Même pattern reste prioritaire ---

    def test_4_meme_pattern_prioritaire(self):
        bib = [HIP_THRUST, SOULEVE_DE_TERRE, FENTE_BULGARE]
        candidats = trouver_alternatives(HIP_THRUST, bib, set(), "Salle complète", [])
        # Fente bulgare ("type" seul) est filtré ; seul Soulevé de terre (pattern hinge) reste.
        self.assertEqual(noms(candidats), ["Soulevé de terre (deadlift)"])
        self.assertIn("pattern_mouvement", candidats[0]["memes_criteres"])

    # --- 5. Même pattern + même groupe reste devant même pattern seul ---

    def test_5_pattern_et_groupe_devant_pattern_seul(self):
        # Pont fessier : pattern hinge + groupe fessiers (comme Hip thrust) -> score 110.
        # Soulevé de terre : pattern hinge seul (groupe chaine_posterieure != fessiers) -> score 100+1(type)=101.
        candidats = trouver_alternatives(HIP_THRUST, [HIP_THRUST, PONT_FESSIER, SOULEVE_DE_TERRE], set(), "Salle complète", [])
        self.assertEqual(noms(candidats), ["Pont fessier (glute bridge)", "Soulevé de terre (deadlift)"])
        self.assertGreater(candidats[0]["score"], candidats[1]["score"])

    # --- 6. Matériel incompatible -> candidat éliminé ---

    def test_6_materiel_incompatible_elimine(self):
        # Hip thrust lui-même nécessite un banc : absent pour "Aucun" et "Haltères".
        candidat_hip_thrust_pour_autre = ex(9, "Hip thrust (fessiers)", "force", "fessiers", "hinge", "fessiers", ["banc"])
        actuel = ex(10, "Pont fessier (glute bridge)", "gainage_prevention", "fessiers", "hinge", "fessiers", [])
        candidats = trouver_alternatives(actuel, [actuel, candidat_hip_thrust_pour_autre], set(), "Aucun", [])
        self.assertEqual(candidats, [])
        candidats_halteres = trouver_alternatives(actuel, [actuel, candidat_hip_thrust_pour_autre], set(), "Haltères", [])
        self.assertEqual(candidats_halteres, [])
        candidats_salle = trouver_alternatives(actuel, [actuel, candidat_hip_thrust_pour_autre], set(), "Salle complète", [])
        self.assertEqual(noms(candidats_salle), ["Hip thrust (fessiers)"])

    # --- 7. Exercice déjà présent -> candidat éliminé (règle non modifiée par l'Étape 7C) ---

    def test_7_exercice_deja_present_elimine(self):
        candidats = trouver_alternatives(
            HIP_THRUST, bibliotheque_par_defaut(), {PONT_FESSIER["id"]}, "Salle complète", []
        )
        self.assertNotIn("Pont fessier (glute bridge)", noms(candidats))

    # --- 8. Aucun candidat pertinent -> liste vide ---

    def test_8_aucun_candidat_pertinent_liste_vide(self):
        candidats = trouver_alternatives(HIP_THRUST, [HIP_THRUST, DEVELOPPE_COUCHE, DEVELOPPE_EPAULES], set(), "Salle complète", [])
        self.assertEqual(candidats, [])

    def test_8_bis_tous_pertinents_deja_dans_seance_liste_vide(self):
        # Les seuls candidats pertinents (hinge) sont tous déjà dans la séance : liste vide,
        # pas de réorganisation automatique (Étape 7C, problème 3 : règle non modifiée).
        deja_presents = {NORDIC_HAMSTRING["id"], PONT_FESSIER["id"], SOULEVE_DE_TERRE["id"]}
        candidats = trouver_alternatives(HIP_THRUST, bibliotheque_par_defaut(), deja_presents, "Salle complète", [])
        self.assertEqual(candidats, [])

    # --- 9. Tri déterministe : même résultat quel que soit l'ordre d'entrée ---

    def test_9_tri_deterministe_independant_de_lordre_entree(self):
        bib = bibliotheque_par_defaut()
        candidats_ordre_1 = trouver_alternatives(HIP_THRUST, bib, set(), "Salle complète", [])
        candidats_ordre_2 = trouver_alternatives(HIP_THRUST, list(reversed(bib)), set(), "Salle complète", [])
        self.assertEqual(noms(candidats_ordre_1), noms(candidats_ordre_2))

    # --- 10. Les 50 annotations existantes sont toutes remontées par exercice_vers_dict() ---

    def test_10_toutes_les_annotations_remontees_par_exercice_vers_dict(self):
        self.assertEqual(len(ANNOTATIONS), 50)
        for nom, annotation in ANNOTATIONS.items():
            faux_orm = SimpleNamespace(
                id=1,
                nom=nom,
                type="force",
                groupe_musculaire="peu importe",
                materiel_requis="peu importe",
                materiel_requis_liste=annotation["materiel_requis_liste"],
                pattern_mouvement=annotation["pattern_mouvement"],
                groupe_musculaire_principal=annotation["groupe_musculaire_principal"],
            )
            resultat = exercice_vers_dict(faux_orm)
            self.assertEqual(resultat["pattern_mouvement"], annotation["pattern_mouvement"], nom)
            self.assertEqual(
                resultat["groupe_musculaire_principal"], annotation["groupe_musculaire_principal"], nom
            )
            self.assertEqual(resultat["materiel_requis_liste"], annotation["materiel_requis_liste"], nom)


class TestMaterielCompatibleListe(unittest.TestCase):
    """Cas supplémentaires ciblés sur materiel_compatible_liste, au-delà de ce que
    trouver_alternatives exerce déjà indirectement."""

    def test_liste_vide_toujours_compatible(self):
        from substitution import materiel_compatible_liste

        candidat = ex(1, "x", "force", "g", None, None, [])
        for categorie in ["Aucun", "Poids du corps", "Haltères", "Salle complète", "Valeur inconnue"]:
            self.assertTrue(materiel_compatible_liste(candidat, categorie), categorie)

    def test_semantique_or_entre_tags(self):
        from substitution import materiel_compatible_liste

        candidat = ex(1, "x", "force", "g", None, None, ["barre", "halteres"])
        self.assertTrue(materiel_compatible_liste(candidat, "Haltères"))
        self.assertFalse(materiel_compatible_liste(candidat, "Aucun"))
        self.assertFalse(materiel_compatible_liste(candidat, "Poids du corps"))
        self.assertTrue(materiel_compatible_liste(candidat, "Salle complète"))

    def test_none_retombe_sur_texte_libre(self):
        from substitution import materiel_compatible_liste

        candidat = ex(1, "x", "force", "g", None, None, None, materiel_requis="aucun")
        self.assertTrue(materiel_compatible_liste(candidat, "Aucun"))


if __name__ == "__main__":
    unittest.main()
