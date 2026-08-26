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
