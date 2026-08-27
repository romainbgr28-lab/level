"""Moteur de décision coaching (User Model V2 -> stratégie déterministe).

Objectif : inverser le flux USER MODEL -> MISTRAL en USER MODEL -> MOTEUR DE
DÉCISION DÉTERMINISTE -> STRATÉGIE -> MISTRAL. Ce module ne fait AUCUN appel
IA : il combine les données structurées du profil (objectifs_v2, contexte_sportif,
disponibilites, niveau_effectif), l'historique et le calendrier en une décision
de coaching structurée (`DecisionCoaching`), traçable (chaque choix porte une
raison textuelle dans `raisons`).

Il ne duplique jamais la logique déjà présente ailleurs : il appelle
regles_seance.generer_recommandation (phase calendaire, type de séance, garde-
fous, ajustement de charge), duree_seance (contraintes de temps) et
user_model_v2 (objectifs hiérarchisés, disponibilités) plutôt que de
réimplémenter ces règles.

Fonction pure, indépendante de FastAPI/SQLAlchemy : prend des dicts en entrée,
retourne un dataclass. Ne lève jamais : à défaut de donnée, produit une
décision plus pauvre mais toujours exploitable (voir `DecisionCoaching`),
pour rester strictement additif au flux existant (main.py doit pouvoir
continuer sans lui en cas de souci).
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

import duree_seance
import regles_seance
import user_model_v2


@dataclass
class DecisionCoaching:
    """Sortie structurée du moteur de décision, injectée dans le prompt Mistral
    comme "stratégie de coaching" avant que Mistral ne concrétise la séance.

    - objectifs_prioritaires : thèmes V2 triés par rang (le plus prioritaire d'abord).
    - objectif_principal / objectif_secondaire : raccourcis pratiques sur les deux premiers
      éléments de objectifs_prioritaires (None si absent) — évite à chaque appelant de
      réindexer la liste, et rend le contrat explicite (cf. spécification P0.5 section 5).
    - qualites_prioritaires : qualités physiques/priorités liées au poste/sport
      (regles_seance.obtenir_priorites_poste), jamais hardcodées football.
    - type_seance_recommande : type de séance déterminé par le moteur de règles
      (regles_seance.generer_recommandation), déjà arbitré phase calendaire >
      gabarit programme > objectifs V2 hiérarchisés > repli legacy. C'est cette
      même valeur (recommandation["type_seance_suggere"]) qui pilote réellement
      la sélection des exercices dans main.py::generer_seance — pas une valeur
      recalculée séparément ici, pour qu'il ne puisse jamais y avoir de
      divergence entre la décision et la séance effectivement générée.
    - focus_principal : phrase courte de synthèse (objectif principal + type de séance),
      utile comme titre de section dans le prompt.
    - niveau_effectif : sous-ensemble pertinent du niveau effectif par qualité
      physique (déclaré recalibré par l'observé, voir user_model_v2).
    - contraintes : liste de contraintes concrètes à respecter (temps dispo,
      matériel, zones à exclure, intensité max) — jamais des suggestions.
    - ajustements : ajustements relatifs de charge/volume (%) par rapport à la
      dernière séance de ce type (regles_seance.calculer_ajustement_charge).
    - raisons : traçabilité complète (pourquoi ce type de séance, cet
      ajustement, ces contraintes) — utile en debug et à injecter telle quelle
      dans le prompt pour que Mistral comprenne le contexte sans le réinventer.
    - confiance_decision : indicateur (0..1) de la fiabilité de la décision de type de
      séance, selon sa source — une contrainte de sécurité calendaire est certaine (1.0),
      un objectif V2 explicite est fiable (0.9), un repli esthétique legacy l'est moins
      (0.6), un repli par défaut sans aucun signal l'est encore moins (0.4). Sert à
      informer Mistral (et un futur débogage) de la robustesse du choix, jamais à le
      remettre en cause automatiquement.
    - recommandation_brute : la recommandation regles_seance.generer_recommandation
      complète (non retravaillée), conservée pour les appelants qui en ont
      encore besoin telle quelle (rétro-compatibilité du flux existant).
    """

    objectifs_prioritaires: list[str] = field(default_factory=list)
    objectif_principal: Optional[str] = None
    objectif_secondaire: Optional[str] = None
    qualites_prioritaires: list[str] = field(default_factory=list)
    type_seance_recommande: str = "force"
    focus_principal: str = ""
    niveau_effectif: dict[str, float] = field(default_factory=dict)
    contraintes: list[str] = field(default_factory=list)
    ajustements: dict[str, float] = field(default_factory=dict)
    raisons: list[str] = field(default_factory=list)
    confiance_decision: float = 0.5
    recommandation_brute: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "objectifs_prioritaires": self.objectifs_prioritaires,
            "objectif_principal": self.objectif_principal,
            "objectif_secondaire": self.objectif_secondaire,
            "qualites_prioritaires": self.qualites_prioritaires,
            "type_seance_recommande": self.type_seance_recommande,
            "focus_principal": self.focus_principal,
            "niveau_effectif": self.niveau_effectif,
            "contraintes": self.contraintes,
            "ajustements": self.ajustements,
            "raisons": self.raisons,
            "confiance_decision": self.confiance_decision,
        }


def _focus_principal(objectifs_prioritaires: list[str], type_seance: str) -> str:
    if objectifs_prioritaires:
        return f"{objectifs_prioritaires[0]} via une séance de type {type_seance}"
    return f"séance de type {type_seance} (aucun objectif V2 déclaré, focus par défaut)"


def _confiance_decision(
    phase: str,
    type_seance_gabarit: Optional[str],
    objectifs_v2_themes: list[str],
    sport: Optional[str],
    objectif_esthetique: Optional[dict[str, Any]],
) -> float:
    """Confiance dans la décision de type de séance, selon sa source réelle (voir
    regles_seance._suggerer_type_seance pour la même hiérarchie). Valeurs fixes et
    documentées plutôt qu'un score composite arbitraire (P0.5 : pas de sur-engineering)."""
    if phase != "phase_normale":
        return 1.0
    if type_seance_gabarit:
        return 0.85
    if objectifs_v2_themes and user_model_v2.type_seance_pour_objectifs(objectifs_v2_themes, sport=sport):
        return 0.9
    if objectif_esthetique and (objectif_esthetique.get("tags") or objectif_esthetique.get("texte_libre")):
        return 0.6
    return 0.4


def _contraintes(
    recommandation: dict[str, Any],
    disponibilites_jour_minutes: Optional[int],
    materiel: Optional[str],
) -> list[str]:
    contraintes: list[str] = []

    intensite_max = recommandation.get("intensite_max")
    if intensite_max:
        contraintes.append(f"intensité maximale autorisée : {intensite_max}")

    exclusions = recommandation.get("exclusions") or []
    if exclusions:
        contraintes.append("zones à exclure impérativement : " + ", ".join(exclusions))

    if disponibilites_jour_minutes is not None:
        contraintes.append(f"temps disponible aujourd'hui : {disponibilites_jour_minutes} min (séance déjà calibrée en conséquence)")

    if materiel:
        contraintes.append(f"matériel disponible : {materiel}")

    return contraintes


def construire_decision(
    profil: dict[str, Any],
    historique: dict[str, Any],
    etat_du_jour: dict[str, Any],
    type_seance_gabarit: Optional[str] = None,
    aujourdhui: Optional[date] = None,
    niveau_effectif: Optional[dict[str, float]] = None,
) -> DecisionCoaching:
    """Construit la décision de coaching structurée pour la séance du jour.

    Réutilise regles_seance.generer_recommandation pour tout ce qui est
    calendaire/historique/garde-fous (pas de duplication de cette logique).
    N'échoue jamais : une donnée manquante (profil incomplet, ancien format)
    produit simplement une décision plus pauvre (listes vides, valeurs par
    défaut), jamais une exception — la génération de séance existante doit
    pouvoir continuer même si l'appelant n'utilise pas cette décision.
    """
    aujourdhui = aujourdhui or date.today()

    try:
        recommandation = regles_seance.generer_recommandation(
            profil, historique, etat_du_jour, type_seance_gabarit=type_seance_gabarit, aujourdhui=aujourdhui
        )
    except Exception:
        # Filet de sécurité : le moteur de décision ne doit jamais faire
        # échouer la génération de séance existante. On retombe sur une
        # recommandation minimale neutre plutôt que de propager l'erreur.
        recommandation = {
            "phase_calendaire": "phase_normale",
            "intensite_max": "normale",
            "priorites_poste": [],
            "type_seance_suggere": type_seance_gabarit or "force",
            "ajustement_charge_pct": 0.0,
            "ajustement_volume_pct": 0.0,
            "raisons": ["Moteur de règles indisponible pour cette requête : décision de repli neutre."],
            "exclusions": [],
        }

    # Objectifs V2 : recommandation.get("objectifs_v2_themes") est déjà le tri fait par
    # regles_seance.generer_recommandation (via user_model_v2.objectifs_ordonnes) — on le
    # réutilise tel quel plutôt que de retrier profil["objectifs_v2"] une seconde fois, sauf
    # filet de sécurité si la recommandation de repli (exception ci-dessus) ne l'a pas renseigné.
    objectifs_prioritaires = recommandation.get("objectifs_v2_themes")
    if objectifs_prioritaires is None:
        objectifs_prioritaires = user_model_v2.objectifs_ordonnes(profil.get("objectifs_v2"))
    type_seance = recommandation.get("type_seance_suggere", "force")

    disponibilites = profil.get("disponibilites") or {}
    jour_abbrev = regles_seance.JOURS_SEMAINE_ABBREV[aujourdhui.weekday()]
    minutes_jour = user_model_v2.minutes_disponibles_jour(disponibilites, jour_abbrev)
    if minutes_jour is None:
        minutes_jour = duree_seance.parser_temps_dispo_minutes(etat_du_jour.get("temps_dispo"))

    raisons = list(recommandation.get("raisons") or [])
    if objectifs_prioritaires:
        raisons.append(
            "Objectif prioritaire déclaré : "
            + objectifs_prioritaires[0]
            + (f" (puis {', '.join(objectifs_prioritaires[1:])})" if len(objectifs_prioritaires) > 1 else "")
        )
    else:
        raisons.append("Aucun objectif V2 déclaré : aucune priorisation d'objectif appliquée.")

    sport = (profil.get("contexte_sportif") or {}).get("sport")
    confiance = _confiance_decision(
        recommandation.get("phase_calendaire", "phase_normale"),
        type_seance_gabarit,
        objectifs_prioritaires,
        sport,
        profil.get("objectif_esthetique"),
    )

    return DecisionCoaching(
        objectifs_prioritaires=objectifs_prioritaires,
        objectif_principal=objectifs_prioritaires[0] if objectifs_prioritaires else None,
        objectif_secondaire=objectifs_prioritaires[1] if len(objectifs_prioritaires) > 1 else None,
        qualites_prioritaires=list(recommandation.get("priorites_poste") or []),
        type_seance_recommande=type_seance,
        focus_principal=_focus_principal(objectifs_prioritaires, type_seance),
        niveau_effectif=niveau_effectif or {},
        contraintes=_contraintes(recommandation, minutes_jour, profil.get("materiel")),
        ajustements={
            "charge_pct": recommandation.get("ajustement_charge_pct", 0.0),
            "volume_pct": recommandation.get("ajustement_volume_pct", 0.0),
        },
        raisons=raisons,
        confiance_decision=confiance,
        recommandation_brute=recommandation,
    )


# ---------------------------------------------------------------------------
# Structure hebdomadaire (P1.0 programme) : USER MODEL -> MOTEUR DÉTERMINISTE
# -> STRUCTURE HEBDOMADAIRE CONTRAIGNANTE -> MISTRAL (détails uniquement).
#
# Réutilise exactement les mêmes briques que la décision par séance ci-dessus
# (user_model_v2.objectifs_ordonnes, user_model_v2._MAPPING_THEME_VERS_TYPE_SEANCE,
# la même règle performance_sport_pratique -> endurance/explosivité_vitesse) :
# aucune deuxième table de correspondance objectif -> type de séance n'est créée
# ici. C'est le seul endroit qui arbitre la répartition des jours ; Mistral et
# le fallback (main.py::_construire_programme_secours) consomment cette même
# fonction, jamais une logique parallèle.
# ---------------------------------------------------------------------------

JOURS_SEMAINE_STRUCTURE = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]

_JOUR_COMPLET_PAR_NOM_LOWER = {j: j for j in JOURS_SEMAINE_STRUCTURE}
# Association avec regles_seance.JOURS_SEMAINE (noms complets capitalisés, tels que stockés
# dans calendrier_matchs.jour_habituel) : même ordre/index, seule la casse diffère.
_NOMS_CAPITALISES = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

# Correction du bug de format de clé identifié en audit : construire_structure_hebdomadaire
# calcule en interne avec des jours complets en minuscules (format aligné sur Profil.disponibilites,
# voir user_model_v2.JOURS_DISPONIBILITES), mais TOUS les lecteurs de Programme.gabarit_hebdomadaire
# (main.py::generer_seance via regles_seance.JOURS_SEMAINE_ABBREV, et le frontend via
# src/utils/programme.ts::JOURS_SEMAINE_ABBREV) attendent des clés abrégées capitalisées
# ("Lun".."Dim"). Sans cette conversion, gabarit_hebdomadaire est stocké en base avec des clés
# ("lundi", "mercredi", ...) qu'aucun consommateur ne recherche jamais : le lookup échoue tous
# les jours, silencieusement, même quand le programme actif prévoit bel et bien une séance
# aujourd'hui. La conversion est appliquée une seule fois, au point de sortie de
# construire_structure_hebdomadaire, pour que tous les consommateurs en aval (validation Mistral,
# repli sans IA, prompt, DB) héritent automatiquement du bon format sans double conversion.
_ABBREV_PAR_JOUR_STRUCTURE: dict[str, str] = dict(zip(JOURS_SEMAINE_STRUCTURE, regles_seance.JOURS_SEMAINE_ABBREV))


def _jour_match_lower(jour_habituel: Optional[str]) -> Optional[str]:
    if not jour_habituel or not isinstance(jour_habituel, str):
        return None
    cible = jour_habituel.strip().lower()
    for j in JOURS_SEMAINE_STRUCTURE:
        if j == cible:
            return j
    return None


def _types_ponderes_depuis_objectifs(
    objectifs_v2_normalises: list[dict[str, Any]], sport: Optional[str]
) -> list[tuple[str, float]]:
    """Convertit les objectifs hiérarchisés (déjà normalisés : theme/rang/poids) en une liste
    (type_de_seance, poids_cumule) triée par ordre de priorité d'apparition, en réutilisant
    STRICTEMENT le mapping thème -> type déjà défini plus haut dans ce module (P0.5), jamais un
    mapping concurrent. perte_de_gras/discipline_mentale ne produisent volontairement aucun type
    (objectifs transversaux, cf. spécification programme section 4/6) : ils sont ignorés ici sans
    faire échouer le calcul, exactement comme dans type_seance_pour_objectifs."""
    themes_ordonnes = [o["theme"] for o in objectifs_v2_normalises if o.get("theme")]
    poids_par_theme = {o["theme"]: float(o.get("poids", 0.0)) for o in objectifs_v2_normalises if o.get("theme")}

    poids_par_type: dict[str, float] = {}
    ordre_apparition: list[str] = []

    for theme in themes_ordonnes:
        type_ = user_model_v2._MAPPING_THEME_VERS_TYPE_SEANCE.get(theme)
        if type_ is None and theme == "performance_sport_pratique":
            type_ = "endurance" if "endurance" in themes_ordonnes else "explosivité_vitesse"
        if type_ is None:
            # perte_de_gras, discipline_mentale ou thème inconnu : transversal, aucun type imposé.
            continue
        if type_ not in poids_par_type:
            ordre_apparition.append(type_)
        poids_par_type[type_] = poids_par_type.get(type_, 0.0) + poids_par_theme.get(theme, 0.0)

    return [(type_, poids_par_type[type_]) for type_ in ordre_apparition]


def _repartir_types_sur_jours(types_ponderes: list[tuple[str, float]], n_jours: int) -> list[str]:
    """Répartit `n_jours` séances entre les types disponibles au prorata de leur poids
    (méthode du plus grand reste), en conservant l'ordre de priorité déclaré : à volume égal,
    le type le plus prioritaire (rang le plus haut) apparaît en premier dans la séquence."""
    if n_jours <= 0:
        return []
    if not types_ponderes:
        return ["force"] * n_jours  # filet de sécurité final, identique au repli de regles_seance.

    total_poids = sum(w for _, w in types_ponderes) or 1.0
    parts = [(type_, (w / total_poids) * n_jours) for type_, w in types_ponderes]
    comptes = {type_: int(part) for type_, part in parts}
    restant = n_jours - sum(comptes.values())

    ordre_reste = sorted(parts, key=lambda x: (x[1] - int(x[1])), reverse=True)
    i = 0
    while restant > 0 and ordre_reste:
        type_ = ordre_reste[i % len(ordre_reste)][0]
        comptes[type_] += 1
        restant -= 1
        i += 1

    sequence: list[str] = []
    for type_, _ in types_ponderes:
        sequence.extend([type_] * comptes.get(type_, 0))
    return sequence[:n_jours] or ["force"] * n_jours


def _objectif_principal_pour_type(type_: str, themes_ordonnes: list[str]) -> str:
    """Nom de l'objectif V2 qui justifie ce type de séance (traçabilité), premier thème
    hiérarchisé qui s'y résout via le même mapping que ci-dessus."""
    for theme in themes_ordonnes:
        mappe = user_model_v2._MAPPING_THEME_VERS_TYPE_SEANCE.get(theme)
        if mappe == type_:
            return theme
        if mappe is None and theme == "performance_sport_pratique":
            resolu = "endurance" if "endurance" in themes_ordonnes else "explosivité_vitesse"
            if resolu == type_:
                return theme
    return "general"


def construire_structure_hebdomadaire(
    objectifs_v2: Any = None,
    sport: Optional[str] = None,
    poste: Optional[str] = None,
    disponibilites: Optional[dict[str, Optional[int]]] = None,
    jour_match_habituel: Optional[str] = None,
    frequence_hebdo: Optional[int] = None,
    objectifs_legacy: Optional[list[str]] = None,
) -> dict[str, dict[str, str]]:
    """Construit la structure hebdomadaire du programme, DÉTERMINISTE et pure (aucune I/O, aucun
    appel réseau/Mistral) : {jour_lower: {"type": type_seance, "objectif_principal": theme}}.

    `frequence_hebdo` est la fréquence de pratique du SPORT (ex. nb d'entraînements de football/
    semaine) — une information de charge sportive, gardée dans la signature pour un usage futur
    (modulation volume/intensité), mais qui NE plafonne PAS le nombre de séances LEVEL retenues
    ici : c'est `disponibilites` (Profil.disponibilites) qui définit le plafond de jours
    utilisables par LEVEL, jamais frequence_hebdo (bug corrigé, cf. audit P1.0).

    Ordre de priorité appliqué (spécification programme section 8, à ne jamais inverser) :
    1. contraintes absolues (jour de match exclu, veille/lendemain de match) ;
    2. objectifs hiérarchisés (rang 1 pèse plus que rang 2, qui pèse plus que rang 3 —
       user_model_v2.POIDS_PAR_RANG, déjà appliqué dans objectifs_v2 normalisé) ;
    3. contexte sportif (le sport ne fait que désambiguïser, jamais n'écrase la hiérarchie —
       cf. user_model_v2.type_seance_pour_objectifs) ;
    4. disponibilités réelles (aucune séance un jour indisponible, aucune séance inventée).

    `sport`/`poste` sont acceptés pour la signature/l'API (contexte sportif du profil) mais
    n'influencent ici que via le mapping objectifs -> type déjà réutilisé (performance_sport_pratique) ;
    le sport pratiqué n'est jamais automatiquement l'objectif principal (spécification section 7).
    """
    disponibilites = disponibilites or {}

    objectifs_v2_normalises = objectifs_v2 if isinstance(objectifs_v2, list) and objectifs_v2 and isinstance(objectifs_v2[0], dict) else None
    if not objectifs_v2_normalises:
        # Compatibilité legacy (spécification section 17.10) : profil ancien sans objectifs_v2
        # exploitable -> on normalise au mieux depuis la liste de libellés legacy, sans jamais
        # planter (user_model_v2.normaliser_objectifs gère déjà ce cas, y compris liste vide).
        objectifs_v2_normalises = user_model_v2.normaliser_objectifs(objectifs_legacy or objectifs_v2 or [])

    themes_ordonnes = user_model_v2.objectifs_ordonnes(objectifs_v2_normalises)
    types_ponderes = _types_ponderes_depuis_objectifs(objectifs_v2_normalises, sport)

    jour_match = _jour_match_lower(jour_match_habituel)
    idx_match = JOURS_SEMAINE_STRUCTURE.index(jour_match) if jour_match else None
    jour_veille = JOURS_SEMAINE_STRUCTURE[(idx_match - 1) % 7] if idx_match is not None else None
    jour_lendemain = JOURS_SEMAINE_STRUCTURE[(idx_match + 1) % 7] if idx_match is not None else None

    # Jours réellement disponibles (minutes non nulles), dans l'ordre de la semaine — jamais
    # une séance un jour indisponible (spécification section 9), et jamais le jour de match
    # lui-même (repos/match, contrainte absolue, spécification section 8).
    jours_disponibles = [
        jour for jour in JOURS_SEMAINE_STRUCTURE
        if disponibilites.get(jour) is not None and jour != jour_match
    ]

    if not jours_disponibles:
        return {}

    # `frequence_hebdo` décrit la fréquence de pratique du SPORT (ex. nb d'entraînements de
    # football/semaine), pas le nombre de séances LEVEL voulues : il ne doit jamais plafonner
    # ici le nombre de jours retenus (bug corrigé — voir audit P1.0). Le plafond réel est
    # `Profil.disponibilites` : tous les jours disponibles pertinents sont considérés, LEVEL
    # décidant ensuite lui-même (contraintes de match, répartition des types) lesquels utiliser.
    n_seances = len(jours_disponibles)

    # Les jours contraints par le calendrier (veille/lendemain de match) sont sélectionnés en
    # priorité s'ils sont disponibles : une contrainte absolue ne doit jamais être évincée par
    # un nombre de séances réduit.
    selection: list[str] = []
    for jour in (jour_veille, jour_lendemain):
        if jour and jour in jours_disponibles and jour not in selection:
            selection.append(jour)
    for jour in jours_disponibles:
        if len(selection) >= n_seances:
            break
        if jour not in selection:
            selection.append(jour)
    selection = selection[:n_seances]
    jours_retenus = [jour for jour in jours_disponibles if jour in selection]

    jours_libres = [jour for jour in jours_retenus if jour not in (jour_veille, jour_lendemain)]
    sequence_types = _repartir_types_sur_jours(types_ponderes, len(jours_libres))

    structure: dict[str, dict[str, str]] = {}
    for jour in jours_retenus:
        if jour == jour_veille:
            structure[jour] = {
                "type": "explosivité_vitesse",
                "objectif_principal": "veille_de_match_activation_legere",
            }
        elif jour == jour_lendemain:
            structure[jour] = {
                "type": "repos",
                "objectif_principal": "recuperation_post_match",
            }
        else:
            idx = jours_libres.index(jour)
            type_ = sequence_types[idx] if idx < len(sequence_types) else (types_ponderes[0][0] if types_ponderes else "force")
            structure[jour] = {
                "type": type_,
                "objectif_principal": _objectif_principal_pour_type(type_, themes_ordonnes),
            }

    # Conversion finale vers le format de clé attendu par tous les consommateurs de
    # Programme.gabarit_hebdomadaire (abrégé capitalisé "Lun".."Dim") -- voir
    # _ABBREV_PAR_JOUR_STRUCTURE ci-dessus. Tout le calcul qui précède reste en jours complets
    # minuscules (aligné sur Profil.disponibilites), seule la sortie change de format.
    return {_ABBREV_PAR_JOUR_STRUCTURE[jour]: info for jour, info in structure.items()}


DUREE_SEMAINES_PROGRAMME_DEFAUT = 8

TYPES_SEANCE_PROGRAMME = ["force", "explosivité_vitesse", "esthétique", "endurance", "repos"]


def normaliser_type_seance_programme(valeur: Optional[str]) -> Optional[str]:
    """Fait correspondre une valeur de gabarit_hebdomadaire à un type canonique de
    TYPES_SEANCE_PROGRAMME, tolérant une casse ou des accents légèrement différents de ce que
    demande le prompt (déjà observé en pratique dans les réponses Mistral). Retourne None si
    aucune correspondance, y compris si la valeur est absente."""
    if not isinstance(valeur, str) or not valeur.strip():
        return None

    def _sans_accents(s: str) -> str:
        for a, b in (("é", "e"), ("è", "e"), ("ê", "e"), ("à", "a")):
            s = s.replace(a, b)
        return s

    cible = _sans_accents(valeur.strip().lower())
    for type_ in TYPES_SEANCE_PROGRAMME:
        if cible == _sans_accents(type_.lower()):
            return type_
    return None


def programme_depuis_structure(structure_hebdomadaire: dict[str, dict[str, str]]) -> dict[str, Any]:
    """Construit le contenu de secours minimal (phases + trajectoire générique) à partir de la
    structure hebdomadaire déterministe — utilisé par le fallback complet (Mistral indisponible,
    voir construire_programme_secours) pour produire un programme minimal exploitable sans IA."""
    gabarit = {jour: info["type"] for jour, info in structure_hebdomadaire.items()}
    progression = [round(100 + i * 5, 1) for i in range(DUREE_SEMAINES_PROGRAMME_DEFAUT)]
    types_presents = set(gabarit.values())

    trajectoire: dict[str, list[float]] = {}
    if "force" in types_presents:
        trajectoire["force"] = progression
    if "explosivité_vitesse" in types_presents:
        trajectoire["explosivite"] = progression
    if "esthétique" in types_presents:
        trajectoire["esthetique"] = progression
    if "endurance" in types_presents:
        trajectoire["endurance"] = progression
    if not trajectoire:
        trajectoire["force"] = progression

    return {
        "phases": [
            {"nom": "adaptation", "semaine_debut": 1, "semaine_fin": 2, "description": "Reprise progressive, apprentissage des mouvements."},
            {"nom": "accumulation", "semaine_debut": 3, "semaine_fin": 6, "description": "Montée en charge et en volume."},
            {"nom": "évaluation", "semaine_debut": 7, "semaine_fin": 8, "description": "Consolidation et bilan des progrès."},
        ],
        "gabarit_hebdomadaire": gabarit,
        "trajectoire_progression": trajectoire,
    }


def construire_programme_secours(structure_hebdomadaire: dict[str, dict[str, str]]) -> dict[str, Any]:
    """Programme de repli, construit sans IA, utilisé par main.py::generer_programme si Mistral
    échoue après retentative. Utilise EXACTEMENT la même structure hebdomadaire déterministe
    (construire_structure_hebdomadaire) que le chemin Mistral : la décision structurelle (jours,
    types) est donc rigoureusement identique dans les deux cas ; seul le contenu de détail
    (phases/trajectoire, ici générique) diffère (spécification programme section 14)."""
    return programme_depuis_structure(structure_hebdomadaire)


def valider_gabarit_contre_structure(
    gabarit_brut: Any, structure_hebdomadaire: dict[str, dict[str, str]]
) -> tuple[dict[str, str], bool]:
    """Valide (déterministe, post-Mistral) que le gabarit_hebdomadaire retourné par Mistral
    respecte la structure imposée : mêmes jours, mêmes types, aucun jour indisponible ajouté,
    aucune séance manquante. Option A de la spécification (section 13) : en cas de divergence, les
    types déviants sont remplacés par les types déterministes attendus (jours de la structure
    exclusivement), plutôt que d'enregistrer un gabarit incohérent en DB. Retourne
    (gabarit_corrige, était_conforme)."""
    attendu = {jour: info["type"] for jour, info in structure_hebdomadaire.items()}
    if not isinstance(gabarit_brut, dict):
        return dict(attendu), False

    normalise: dict[str, str] = {}
    for jour, type_brut in gabarit_brut.items():
        if jour not in attendu:
            continue  # jour hors structure (indisponible ou inventé) : jamais retenu.
        normalise[jour] = normaliser_type_seance_programme(type_brut)

    conforme = normalise == attendu
    return dict(attendu), conforme


def formater_structure_hebdomadaire_prompt(structure: dict[str, dict[str, str]]) -> str:
    """Formate la structure hebdomadaire déterministe en section de prompt injectée dans
    generer_programme (main.py), marquée comme non négociable (spécification section 12)."""
    if not structure:
        lignes = "(aucun jour disponible : aucune séance à générer)"
    else:
        lignes = "\n".join(
            f"- {jour} : type imposé « {info['type']} » (objectif : {info['objectif_principal']})"
            for jour, info in structure.items()
        )
    return f"""DÉCISION STRUCTURELLE DU COACH — NE PAS MODIFIER (moteur déterministe, non négociable) :
{lignes}

Tu NE choisis PAS les jours d'entraînement, tu NE changes PAS les types de séance ci-dessus,
tu N'AJOUTES aucune séance un autre jour, tu N'EN SUPPRIMES aucune. Tu peux uniquement détailler
le contenu de chaque séance (exercices, séries, répétitions, durée, progression, phase, récupération)."""


def formater_section_prompt(decision: DecisionCoaching) -> str:
    """Formate la décision en section de prompt, injectée avant la consigne de
    génération concrète de la séance (voir main.py::_construire_prompt_generation).

    Sépare explicitement (P0.5 section 7) :
    - "DÉCISION DU COACH" : le type de séance et les objectifs sont IMPOSÉS,
      Mistral ne les redéfinit ni ne les réinterprète — il n'a pas le choix du
      type de séance, seulement de la façon de le concrétiser.
    - "DÉTAILS À GÉNÉRER" : ce que Mistral doit effectivement produire à partir
      de cette décision déjà arbitrée (contraintes, ajustements, niveau)."""
    objectifs_txt = ", ".join(decision.objectifs_prioritaires) or "aucun objectif V2 déclaré"
    qualites_txt = ", ".join(decision.qualites_prioritaires) or "aucune priorité spécifique"
    contraintes_txt = "\n".join(f"- {c}" for c in decision.contraintes) or "- aucune contrainte particulière"
    raisons_txt = "; ".join(decision.raisons) or "aucune"
    niveau_txt = ", ".join(f"{q} : {v}" for q, v in decision.niveau_effectif.items()) or "non disponible"

    return f"""VOICI LA DÉCISION DU COACH — TU DOIS LA RESPECTER (moteur de décision déterministe,
non négociable ; tu concrétises cette décision, tu ne la redéfinis pas) :
- TYPE DE SÉANCE IMPOSÉ : {decision.type_seance_recommande}
- OBJECTIF PRINCIPAL : {decision.objectif_principal or "aucun"}
- OBJECTIF SECONDAIRE : {decision.objectif_secondaire or "aucun"}
- Objectifs prioritaires (ordre décroissant) : {objectifs_txt}
- Focus de la séance : {decision.focus_principal}
- Confiance dans cette décision : {decision.confiance_decision:.2f}

VOICI LES DÉTAILS À GÉNÉRER à partir de cette décision :
- Qualités physiques prioritaires : {qualites_txt}
- Niveau effectif par qualité : {niveau_txt}
- Contraintes à respecter :
{contraintes_txt}
- Ajustement charge/volume par rapport à la dernière séance de ce type : charge {decision.ajustements.get('charge_pct', 0.0):+.0f}%, volume {decision.ajustements.get('volume_pct', 0.0):+.0f}%
- Raisons de cette décision : {raisons_txt}"""
