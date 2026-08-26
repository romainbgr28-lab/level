"""User Model V2 : objectifs hiérarchisés, contexte sportif, disponibilités
structurées et niveau déclaré/observé/effectif.

Code Python pur (pas d'IA, pas de FastAPI) : fonctions de normalisation et de
calcul réutilisées par schemas.py (validation) et main.py (génération).
Toute fonction ici est censée être idempotente sur une donnée déjà au format
V2 : ré-appliquer la normalisation à une donnée déjà normalisée ne doit rien
changer.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger("level")


# ---------------------------------------------------------------------------
# Objectifs V2
# ---------------------------------------------------------------------------

THEMES_OBJECTIFS_V2 = [
    "esthetique_hypertrophie",
    "force",
    "perte_de_gras",
    "performance_sport_pratique",
    "endurance",
    "discipline_mentale",
]

MAX_OBJECTIFS_ACTIFS = 3

# Poids par défaut selon le rang (1 = priorité principale). Mécanisme de
# priorisation pour le moteur de règles / Mistral, jamais une contrainte dure.
POIDS_PAR_RANG = {1: 0.6, 2: 0.3, 3: 0.1}

# Mapping des anciens libellés texte libre (objectifs = ["Force", "Endurance", ...])
# vers les thèmes V2. Les clés sont comparées en minuscule/sans accents. Toute
# valeur non trouvée ici n'est jamais silencieusement ignorée : voir
# migrer_objectifs_legacy ci-dessous, qui logue et documente le cas au lieu
# d'inventer un mapping.
MAPPING_ANCIENS_OBJECTIFS: dict[str, str] = {
    "force": "force",
    "endurance": "endurance",
    "hypertrophie": "esthetique_hypertrophie",
    "esthetique": "esthetique_hypertrophie",
    "esthétique": "esthetique_hypertrophie",
    "hypertrophie/esthetique": "esthetique_hypertrophie",
    "hypertrophie / esthetique": "esthetique_hypertrophie",
    "perte de poids": "perte_de_gras",
    "perte de gras": "perte_de_gras",
    "perte de poids/gras": "perte_de_gras",
    "perte de poids / gras": "perte_de_gras",
    "performance foot": "performance_sport_pratique",
    "performance football": "performance_sport_pratique",
    "performance sportive": "performance_sport_pratique",
    "performance foot/sport": "performance_sport_pratique",
    "performance sport": "performance_sport_pratique",
    "mental": "discipline_mentale",
    "discipline": "discipline_mentale",
    "mental/discipline": "discipline_mentale",
    "mental / discipline": "discipline_mentale",
    "discipline mentale": "discipline_mentale",
}


def _sans_accents(s: str) -> str:
    for a, b in (("é", "e"), ("è", "e"), ("ê", "e"), ("à", "a"), ("î", "i")):
        s = s.replace(a, b)
    return s


def _cle_mapping(libelle: str) -> str:
    return _sans_accents(libelle.strip().lower())


def poids_par_defaut(rangs: list[int]) -> dict[int, float]:
    """Calcule les poids par défaut pour une liste de rangs (1..3).

    Un seul objectif -> poids 1.0 (quel que soit son rang déclaré, pour rester
    cohérent avec la règle « un seul objectif = poids 1.0 »).
    """
    if len(rangs) == 1:
        return {rangs[0]: 1.0}
    return {rang: POIDS_PAR_RANG.get(rang, 0.0) for rang in rangs}


def normaliser_objectifs(objectifs_bruts: Any) -> list[dict]:
    """Normalise une liste d'objectifs (ancien format list[str] ou nouveau
    format list[dict{theme,rang,poids}]) vers le format V2 canonique :
    list[{"theme": str, "rang": int, "poids": float}], triée par rang, poids
    recalculés selon le rang (jamais fournis par le client - voir Phase 2 :
    "le frontend ne doit pas être source de vérité sur les poids").

    - Limite à MAX_OBJECTIFS_ACTIFS (les objectifs excédentaires sont
      abandonnés, dans l'ordre d'arrivée -> les 3 premiers priment).
    - Idempotente : ré-appliquée à une sortie déjà normalisée, ne change rien
      d'autre que le recalcul des poids (toujours déterministe pour un même
      ensemble de rangs).
    - Ne perd jamais silencieusement une donnée non reconnue (ancien libellé
      sans mapping) : loggée en warning et ignorée individuellement plutôt que
      de faire échouer toute la normalisation ou d'inventer un thème.
    """
    if not objectifs_bruts:
        return []

    themes: list[str] = []

    for item in objectifs_bruts:
        theme: Optional[str] = None
        if isinstance(item, dict):
            theme_brut = item.get("theme")
            if isinstance(theme_brut, str):
                theme = theme_brut.strip()
        elif isinstance(item, str):
            libelle = item.strip()
            cle = _cle_mapping(libelle)
            if cle in THEMES_OBJECTIFS_V2:
                theme = cle
            elif cle in MAPPING_ANCIENS_OBJECTIFS:
                theme = MAPPING_ANCIENS_OBJECTIFS[cle]
            else:
                logger.warning(
                    "[user_model_v2] Objectif legacy sans mapping V2 connu, ignoré : %r "
                    "(ajouter une entrée dans MAPPING_ANCIENS_OBJECTIFS si ce libellé est légitime)",
                    libelle,
                )
                continue

        if theme is None or theme not in THEMES_OBJECTIFS_V2:
            logger.warning("[user_model_v2] Objectif ignoré, thème invalide ou absent : %r", item)
            continue

        if theme not in themes:  # dédoublonnage silencieux (même thème répété)
            themes.append(theme)

    themes = themes[:MAX_OBJECTIFS_ACTIFS]
    rangs = list(range(1, len(themes) + 1))
    poids = poids_par_defaut(rangs)

    return [{"theme": theme, "rang": rang, "poids": poids[rang]} for rang, theme in zip(rangs, themes)]


# ---------------------------------------------------------------------------
# Contexte sportif (sport pratiqué != objectif)
# ---------------------------------------------------------------------------


POSTES_FOOTBALL = ["Gardien", "Défenseur", "Milieu", "Attaquant"]


def normaliser_contexte_sportif(data: Any, poste_legacy: Optional[str] = None) -> dict:
    """Normalise le contexte sportif {sport, frequence_hebdo, poste}.

    RÈGLE FONDAMENTALE : ce sport pratiqué n'implique jamais automatiquement
    un objectif. Cette fonction ne touche jamais à `objectifs`.

    `poste_legacy` : uniquement utilisé pour la migration d'un ancien profil qui
    n'a jamais eu de contexte_sportif explicite (l'app n'a longtemps été que
    football, `poste` était toujours une position de football) — sert
    uniquement à inférer `sport="football"` pour ne pas régresser le
    comportement existant. Un client V2 qui envoie explicitement
    contexte_sportif (même avec sport=None) n'est jamais affecté par ce
    fallback : voir schemas.py::ProfilBase pour la distinction.
    """
    if not isinstance(data, dict):
        data = {}

    sport = data.get("sport")
    if isinstance(sport, str):
        sport = sport.strip() or None

    if sport is None and poste_legacy in POSTES_FOOTBALL:
        sport = "football"

    frequence = data.get("frequence_hebdo")
    try:
        frequence = int(frequence) if frequence is not None else None
    except (TypeError, ValueError):
        frequence = None

    poste = data.get("poste") or poste_legacy
    if isinstance(poste, str):
        poste = poste.strip() or None
    # Le poste n'a de sens que pour le football (voir Phase 2 : "poste pertinent
    # seulement si football") ; on ne l'invente pas pour un autre sport.
    if sport != "football":
        poste = None

    return {"sport": sport, "frequence_hebdo": frequence, "poste": poste}


# ---------------------------------------------------------------------------
# Priorités par sport (remplace PRIORITES_POSTE hardcodé football)
# ---------------------------------------------------------------------------

PRIORITES_PAR_SPORT: dict[str, dict[str, list[str]]] = {
    "football": {
        "Défenseur": ["force_duels", "explosivité_verticale", "jeu_aérien"],
        "Milieu": ["endurance_intermittente", "coordination", "répétition_efforts"],
        "Attaquant": ["vitesse_linéaire", "explosivité_réactive", "finition_puissance"],
        "Gardien": ["explosivité_réactive", "souplesse", "réflexes"],
    },
}

# Fallback générique quand le sport n'est pas couvert par PRIORITES_PAR_SPORT
# (ou absent) : pas de contexte sport-spécifique injecté, priorités neutres.
PRIORITES_GENERIQUES: list[str] = []


def obtenir_priorites(sport: Optional[str], poste: Optional[str]) -> list[str]:
    priorites_sport = PRIORITES_PAR_SPORT.get(sport or "", {})
    return list(priorites_sport.get(poste or "", PRIORITES_GENERIQUES))


# ---------------------------------------------------------------------------
# Disponibilités structurées
# ---------------------------------------------------------------------------

JOURS_DISPONIBILITES = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]

# Même ordre/index que regles_seance.JOURS_SEMAINE_ABBREV (date.weekday() : 0 = lundi).
_ABBREV_PAR_JOUR = dict(zip(JOURS_DISPONIBILITES, ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]))
_JOUR_PAR_ABBREV_LOWER = {v.lower(): k for k, v in _ABBREV_PAR_JOUR.items()}
_JOUR_PAR_NOM_COMPLET_LOWER = {
    "lundi": "lundi", "mardi": "mardi", "mercredi": "mercredi", "jeudi": "jeudi",
    "vendredi": "vendredi", "samedi": "samedi", "dimanche": "dimanche",
}


def disponibilites_vides() -> dict[str, Optional[int]]:
    return {jour: None for jour in JOURS_DISPONIBILITES}


def _parser_ancien_format_contraintes_temps(texte: str) -> dict[str, Optional[int]]:
    """Parse au mieux l'ancien format libre `contraintes_temps`, ex:
    "Lun/Mer/Ven · 45 min/séance" -> jours abrégés + une durée uniforme.

    Best-effort, ne doit jamais lever : en cas de format non reconnu, retourne
    des disponibilités toutes à None (aucune invention de donnée)."""
    dispo = disponibilites_vides()
    if not texte or not isinstance(texte, str):
        return dispo

    partie_jours = texte.split("·")[0]
    partie_duree = texte.split("·")[1] if "·" in texte else ""

    duree_min: Optional[int] = None
    if partie_duree:
        chiffres = "".join(c for c in partie_duree if c.isdigit())
        if chiffres:
            try:
                duree_min = int(chiffres)
            except ValueError:
                duree_min = None

    for token in partie_jours.split("/"):
        token = token.strip().lower()
        if not token:
            continue
        jour = _JOUR_PAR_ABBREV_LOWER.get(token) or _JOUR_PAR_NOM_COMPLET_LOWER.get(token)
        if jour:
            dispo[jour] = duree_min

    return dispo


def normaliser_disponibilites(data: Any, fallback_contraintes_temps: Optional[str] = None) -> dict[str, Optional[int]]:
    """Normalise vers {jour_minuscule: minutes|None} pour les 7 jours.

    Accepte :
    - un dict déjà structuré (nouveau format), complété avec les jours manquants (None) ;
    - None/absent -> fallback sur le parsing best-effort de l'ancien `contraintes_temps`.
    Idempotente : un dict déjà complet en entrée ressort identique.
    """
    if isinstance(data, dict) and data:
        dispo = disponibilites_vides()
        for jour, minutes in data.items():
            jour_norm = str(jour).strip().lower()
            if jour_norm not in dispo:
                continue
            if minutes is None:
                dispo[jour_norm] = None
                continue
            try:
                dispo[jour_norm] = max(0, int(minutes))
            except (TypeError, ValueError):
                dispo[jour_norm] = None
        return dispo

    if fallback_contraintes_temps:
        return _parser_ancien_format_contraintes_temps(fallback_contraintes_temps)

    return disponibilites_vides()


def jours_dispo_abbrev(disponibilites: dict[str, Optional[int]]) -> list[str]:
    """Liste des jours (abréviation "Lun".."Dim", même convention que
    regles_seance.JOURS_SEMAINE_ABBREV) où le joueur est disponible (minutes
    non nulles), dans l'ordre de la semaine. Lecture directe du dict, aucun
    parsing de chaîne."""
    disponibilites = disponibilites or {}
    return [
        _ABBREV_PAR_JOUR[jour]
        for jour in JOURS_DISPONIBILITES
        if disponibilites.get(jour) is not None
    ]


def minutes_disponibles_jour(disponibilites: dict[str, Optional[int]], jour_abbrev: str) -> Optional[int]:
    jour = _JOUR_PAR_ABBREV_LOWER.get(jour_abbrev.lower())
    if not jour:
        return None
    return (disponibilites or {}).get(jour)


# ---------------------------------------------------------------------------
# Niveau déclaré / observé / effectif
# ---------------------------------------------------------------------------

QUALITES_PHYSIQUES = ["force", "explosivite", "vitesse", "endurance"]

# Nombre de séances "comparables" (même qualité sollicitée) au-delà duquel la
# confiance dans le niveau observé est considérée quasi maximale. Valeur
# choisie arbitrairement raisonnable, documentée et facilement modifiable.
SEANCES_POUR_CONFIANCE_MAX = 10


def calculer_confiance(nb_seances_comparables: int) -> float:
    """Confiance (0..1) dans le niveau observé, fonction croissante et bornée
    du nombre de séances comparables. Pas de seuil brutal : approche 1
    progressivement (1 - decroissance exponentielle), jamais de saut net.

    confiance(0) = 0, confiance(SEANCES_POUR_CONFIANCE_MAX) ≈ 0.86,
    tend vers 1 sans jamais l'atteindre exactement (asymptote), et une seule
    séance ne représente qu'une confiance faible (~0.1).
    """
    n = max(0, nb_seances_comparables)
    if n == 0:
        return 0.0
    # 1 - e^(-n/k) avec k choisi pour que n = SEANCES_POUR_CONFIANCE_MAX -> ~0.86.
    k = SEANCES_POUR_CONFIANCE_MAX / 2
    import math

    return round(1 - math.exp(-n / k), 4)


def calculer_niveau_effectif(
    niveau_declare: float, niveau_observe: Optional[float], confiance: float
) -> float:
    """Niveau effectif utilisé pour calibrer le système : interpolation
    linéaire entre le niveau déclaré et le niveau observé, pondérée par la
    confiance dans l'observation.

    effectif = declare * (1 - confiance) + observe * confiance

    - confiance=0 (aucune donnée observée) -> effectif = déclaré.
    - confiance proche de 1 (beaucoup de séances cohérentes) -> effectif
      converge vers l'observé.
    - Transition progressive et continue en fonction de la confiance : pas de
      seuil brutal (voir calculer_confiance). Une seule séance ne peut donc
      jamais faire basculer brutalement le niveau puisque sa confiance
      associée reste faible.
    """
    confiance = min(1.0, max(0.0, confiance))
    if niveau_observe is None:
        return round(niveau_declare, 2)
    return round(niveau_declare * (1 - confiance) + niveau_observe * confiance, 2)


def calculer_niveau_observe(seances_qualite: list[dict[str, Any]]) -> Optional[float]:
    """Recalcule un niveau observé (échelle 1-5, même échelle que les niveaux
    déclarés) à partir de séances réalisées pertinentes pour une qualité
    physique donnée.

    seances_qualite : liste de {"rpe": int|None, "pourcentage_complete": float|None}
    triée par date croissante (peu importe l'ordre en réalité, non utilisé ici
    au-delà de la moyenne — reste volontairement conservateur : pas de
    détection de tendance/progression tant que les données ne le permettent
    pas clairement, voir Phase 5).

    Retourne None si aucune donnée exploitable (n'invente jamais une mesure).
    Heuristique volontairement simple et documentée :
    - RPE moyen autour de 6-7 avec complétion élevée (>=85%) -> le niveau
      décrit par le joueur semble cohérent avec ce qu'il encaisse : score neutre (3.0).
    - RPE moyen bas (<5) avec forte complétion -> les séances semblent trop
      faciles pour le niveau déclaré -> score observé plus haut (jusqu'à 5.0).
    - RPE moyen élevé (>8) et/ou complétion faible (<60%) -> les séances
      semblent trop dures pour le niveau déclaré -> score observé plus bas
      (jusqu'à 1.0).
    """
    donnees = [
        s for s in seances_qualite
        if s.get("rpe") is not None or s.get("pourcentage_complete") is not None
    ]
    if not donnees:
        return None

    rpe_valeurs = [s["rpe"] for s in donnees if s.get("rpe") is not None]
    completions = [s["pourcentage_complete"] for s in donnees if s.get("pourcentage_complete") is not None]

    rpe_moyen = sum(rpe_valeurs) / len(rpe_valeurs) if rpe_valeurs else None
    completion_moyenne = sum(completions) / len(completions) if completions else None

    score = 3.0  # neutre par défaut (pas assez d'info pour trancher)

    if rpe_moyen is not None:
        if rpe_moyen < 5:
            score = 4.0
        elif rpe_moyen > 8:
            score = 1.5
        elif rpe_moyen > 7:
            score = 2.0
        else:
            score = 3.0

    if completion_moyenne is not None:
        if completion_moyenne < 60:
            score = min(score, 2.0)
        elif completion_moyenne >= 95 and (rpe_moyen is None or rpe_moyen < 6):
            score = max(score, 4.0)

    return round(max(1.0, min(5.0, score)), 2)
