"""Coach conversationnel LEVEL : interprétation, orchestration, langage.

Ce module tient la boucle décrite par la spécification V0 :

    message -> interprétation -> décision LEVEL -> action métier -> données mises à jour -> réponse

et surtout la règle qui la rend crédible (section 18) : **le LLM n'est pas le moteur de
décision**. Il n'a ici aucun moyen d'écrire en base ni de calculer une charge, un volume ou
un planning. Tout ce qu'il peut faire, c'est choisir une action de ``coach_actions.ACTIONS``
avec ses arguments ; c'est le moteur qui décide et qui persiste, et le LLM reformule le
résultat.

Concrètement, la seule surface d'écriture exposée au modèle est la liste ``OUTILS``
ci-dessous, et chaque outil y est le miroir exact d'une action métier. Un programme, une
progression de charge ou une semaine « improvisés » par le modèle ne peuvent donc pas
atteindre la base : ils n'auraient aucun chemin pour y aller.

Testabilité : ``repondre()`` prend un ``appel_llm`` injectable. Les tests font tourner toute
la boucle (y compris les exécutions d'actions et les écritures réelles en base) avec un
modèle factice scripté, sans clé API ni réseau — voir test_coach_orchestration.py.
"""

import json
import logging
from datetime import date
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

import coach_actions
import coach_contexte
import mistral_client
import models
import schemas

logger = logging.getLogger("level.coach")

# Nombre maximal d'allers-retours modèle <-> actions pour un seul message utilisateur. Assez
# pour enchaîner « chercher l'exercice, puis enregistrer, puis relire la progression », mais
# borné : au-delà, on renvoie ce qu'on a plutôt que de boucler indéfiniment (et de facturer).
MAX_TOURS = 5

# Messages de conversation réinjectés comme contexte de dialogue. Court volontairement : la
# mémoire de LEVEL est dans la base, pas dans le fil (section 24). Le coach doit rester juste
# même si le fil est vide — c'est ce que vérifie test_coach_orchestration.
MAX_MESSAGES_HISTORIQUE = 10


def _schema(proprietes: dict[str, Any], requis: Optional[list[str]] = None) -> dict[str, Any]:
    return {"type": "object", "properties": proprietes, "required": requis or []}


_STR = {"type": "string"}
_INT = {"type": "integer"}
_NUM = {"type": "number"}
_BOOL = {"type": "boolean"}


def _outil(nom: str, description: str, parametres: dict[str, Any]) -> dict[str, Any]:
    return {"type": "function", "function": {"name": nom, "description": description, "parameters": parametres}}


# Catalogue des outils exposés au modèle. Chaque entrée correspond à une clé de
# coach_actions.ACTIONS (vérifié par test_coach_orchestration::test_outils_et_actions_alignes :
# un outil sans action, ou une action sans outil, fait échouer les tests).
OUTILS: list[dict[str, Any]] = [
    _outil(
        "get_profil",
        "Lit le profil complet : âge, poids, niveau, sport pratiqué, objectifs hiérarchisés, "
        "disponibilités, matériel. À utiliser avant toute réponse qui dépend de qui est l'utilisateur.",
        _schema({}),
    ),
    _outil(
        "get_programme",
        "Lit le programme actif : phases, semaine type (gabarit hebdomadaire), trajectoire de progression.",
        _schema({}),
    ),
    _outil(
        "generer_programme",
        "Construit et ENREGISTRE le programme avec le moteur LEVEL. À utiliser après l'onboarding, "
        "ou quand l'utilisateur demande explicitement un nouveau programme (regenerer=true). "
        "N'écris jamais un programme toi-même : c'est le moteur qui le construit.",
        _schema({"regenerer": _BOOL}),
    ),
    _outil(
        "get_contexte_jour",
        "Décision du jour calculée par le moteur : jour de match, de repos, indisponible ou de séance, "
        "type de séance prévu, position dans le programme, vue de la semaine, prochaine séance.",
        _schema({}),
    ),
    _outil(
        "get_seance_du_jour",
        "La séance prévue aujourd'hui avec ses exercices, séries, répétitions et charges. "
        "La génère via le moteur si elle n'existe pas encore (generer=true par défaut). "
        "TOUJOURS utiliser ceci pour répondre à « je fais quoi aujourd'hui ? » — ne jamais inventer une séance.",
        _schema({"generer": _BOOL}),
    ),
    _outil(
        "get_historique",
        "Les dernières séances réellement terminées : date, type, RPE, pourcentage complété, exercices réalisés.",
        _schema({"limite": _INT}),
    ),
    _outil(
        "get_progression_exercice",
        "Progression réelle sur un exercice, séance par séance (charges, répétitions, RPE). "
        "Obligatoire avant toute affirmation sur la progression : ne jamais estimer une tendance de tête. "
        "Si assez_de_donnees est false, dis-le au lieu d'inventer.",
        _schema({"nom": _STR, "exercice_id": _INT}),
    ),
    _outil(
        "get_bilan",
        "Bilan de la période écoulée calculé à partir des séances terminées et des séries loguées.",
        _schema({"jours": _INT}),
    ),
    _outil(
        "get_contexte_signale",
        "Contraintes actuellement actives déclarées par l'utilisateur : douleurs, fatigue, contraintes.",
        _schema({}),
    ),
    _outil(
        "chercher_exercice",
        "Traduit un nom d'exercice dit en langage naturel en exercice de la bibliothèque LEVEL. "
        "Si la réponse contient choix_possibles ou clarification_requise, pose la question à "
        "l'utilisateur au lieu de choisir à sa place.",
        _schema({"nom": _STR}, ["nom"]),
    ),
    _outil(
        "enregistrer_performance",
        "Enregistre une performance réellement effectuée sur un exercice (séries, répétitions, charge, "
        "difficulté ressentie). series et repetitions sont OBLIGATOIRES : si l'utilisateur ne les a pas "
        "donnés, demande-les, n'appelle pas cet outil avec des valeurs supposées. "
        "difficulte vaut 'facile', 'comme_prevu' ou 'dur'. charge_kg est la charge en kg (omise au poids du corps).",
        _schema(
            {
                "nom": _STR,
                "exercice_id": _INT,
                "series": _INT,
                "repetitions": _INT,
                "charge_kg": _NUM,
                "difficulte": {"type": "string", "enum": list(coach_actions.DIFFICULTES_VALIDES)},
            },
            ["series", "repetitions"],
        ),
    ),
    _outil(
        "terminer_seance",
        "Clôture la séance du jour : écrit l'historique, l'XP et le streak. À appeler quand l'utilisateur "
        "a fini de raconter sa séance et que toutes les performances ont été enregistrées.",
        _schema({"seance_id": _INT, "note": _STR, "duree_reelle_min": _INT, "zone_sensible": _STR}),
    ),
    _outil(
        "adapter_seance",
        "Adapte la séance d'AUJOURD'HUI et enregistre le résultat. motif='duree' avec "
        "minutes_disponibles quand l'utilisateur a moins de temps ; motif='fatigue' quand il est fatigué ; "
        "motif='materiel' avec materiel quand il n'a pas son matériel habituel. "
        "C'est le moteur qui décide quoi retirer — contente-toi d'expliquer le résultat.",
        _schema(
            {
                "motif": {"type": "string", "enum": ["duree", "fatigue", "materiel"]},
                "minutes_disponibles": _INT,
                "materiel": _STR,
            },
            ["motif"],
        ),
    ),
    _outil(
        "proposer_alternatives",
        "Propose 1 à 3 exercices de substitution pour un exercice de la séance du jour, sans rien appliquer. "
        "À utiliser quand l'utilisateur ne peut pas faire un exercice (matériel manquant, gêne).",
        _schema({"nom": _STR, "exercice_id": _INT}),
    ),
    _outil(
        "remplacer_exercice",
        "Applique le remplacement d'un exercice de la séance du jour, une fois le choix fait.",
        _schema({"nom_actuel": _STR, "exercice_id_actuel": _INT, "nom_nouveau": _STR, "exercice_id_nouveau": _INT}),
    ),
    _outil(
        "signaler_douleur",
        "Enregistre une douleur signalée et exclut la zone des prochaines séances. "
        "zone doit être l'une de : jambes, dos, épaules, bras, mollets, abdos. "
        "persistante=true si la douleur dure ou inquiète. Ne pose JAMAIS de diagnostic.",
        _schema({"zone": _STR, "details": _STR, "persistante": _BOOL}, ["zone"]),
    ),
    _outil(
        "signaler_fatigue",
        "Enregistre une fatigue déclarée et allège la séance du jour (volume réduit, charges inchangées).",
        _schema({"details": _STR, "adapter": _BOOL}),
    ),
    _outil(
        "deplacer_match",
        "Met à jour le calendrier de matchs puis fait réévaluer la semaine par le moteur. "
        "Pour déplacer un match : nouvelle_date (AAAA-MM-JJ) ET date_annulee (la date initiale). "
        "Pour changer le jour habituel de match : jour_habituel ('Samedi', 'Dimanche'...).",
        _schema({"nouvelle_date": _STR, "date_annulee": _STR, "jour_habituel": _STR}),
    ),
    _outil(
        "mettre_a_jour_disponibilites",
        "Change les jours et durées d'entraînement disponibles, ce qui reconstruit le programme. "
        "disponibilites est un objet partiel, ex: {\"jeudi\": null, \"vendredi\": 60} "
        "(null = indisponible, sinon minutes). Les jours non cités ne changent pas.",
        _schema({"disponibilites": {"type": "object"}}, ["disponibilites"]),
    ),
    _outil(
        "mettre_a_jour_materiel",
        "Change durablement le matériel du profil (pas seulement pour aujourd'hui : pour ça, utilise "
        "adapter_seance avec motif='materiel'). Valeurs : Aucun, Poids du corps, Haltères, Salle complète.",
        _schema({"materiel": _STR}, ["materiel"]),
    ),
]


SYSTEM_PROMPT = """Tu es LEVEL, le coach sportif personnel de cet utilisateur. Tu le connais déjà.

TON RÔLE
Tu interprètes ce qu'il dit, tu déclenches les bonnes actions du moteur LEVEL, et tu expliques
le résultat. Tu n'es PAS le moteur de décision : les programmes, les charges, les volumes, les
progressions et les réorganisations de planning sont calculés par le moteur via les outils.

RÈGLES ABSOLUES
1. Ne jamais inventer une séance, une charge, un volume, une progression ou une statistique.
   Si tu as besoin d'une information, appelle l'outil correspondant. Si l'outil ne renvoie pas
   la donnée, dis-le simplement.
2. Ne jamais laisser une information importante seulement dans la conversation. Une performance
   racontée s'enregistre (enregistrer_performance), une douleur se signale (signaler_douleur),
   un match déplacé se met à jour (deplacer_match). Annoncer un changement sans appeler l'outil
   est une faute.
3. Si une information est ambiguë ou insuffisante, pose UNE question courte. N'invente pas de
   valeurs par défaut. Exemple : « développé incliné lourd » -> demande les séries et les reps.
   Mais « 24 kg, 4x8, assez facile » est suffisant : enregistre directement, sans demander confirmation.
4. Quand un outil renvoie clarification_requise ou choix_possibles, pose la question telle quelle
   à l'utilisateur, brièvement.
5. Douleur : n'avance jamais de cause ni de diagnostic. Propose d'arrêter l'exercice concerné et
   une adaptation prudente. Si la douleur est persistante, importante ou inquiétante, recommande
   de consulter un professionnel de santé.

TON STYLE
Direct, naturel, concis, compétent. Tu tutoies. Pas de formule d'accueil (« Bonjour, je suis votre
assistant... ») : l'utilisateur te connaît. Pas de murs de texte. Par défaut : la décision, une
justification courte si elle apporte quelque chose, puis la suite.
Exemples du ton attendu :
- « Tu as haut du corps aujourd'hui. 42 minutes. »
- « C'est enregistré. 24 kg sur 4x8, difficulté facile. Je garde ça pour ajuster ta prochaine séance. »
- « D'accord, 25 minutes. Je garde les exercices prioritaires et je réduis le volume. »

CONFIRMATIONS
Prends seul les petites décisions. Ne demande confirmation que pour un changement structurant
(déplacer une séance, reconstruire le programme) : « Je peux déplacer ta séance de jeudi à
vendredi. Je le fais ? ». Cela doit rester rare.

CE QUE LEVEL SAIT DE L'UTILISATEUR MAINTENANT
{contexte}
"""


def construire_contexte(db: Session, today: date) -> dict[str, Any]:
    """Snapshot compact injecté dans le prompt (voir coach_contexte.py).

    Lecture seule : aucune séance n'est générée par le simple fait d'ouvrir la conversation —
    c'est ``get_seance_du_jour`` qui le fait, et seulement si le coach en a besoin.
    """
    import main

    profil = coach_actions._profil_dict(db)
    programme = main.get_programme_actif(db=db)
    contexte_jour = main.get_contexte_jour(db=db, today=today)
    seance = coach_actions._seance_du_jour(db, today)

    return coach_contexte.construire_contexte(
        profil=profil,
        programme=(
            schemas.ProgrammeOut.model_validate(programme).model_dump(mode="json") if programme else None
        ),
        contexte_jour=contexte_jour,
        seance_du_jour=(
            {
                **schemas.SeanceOut.model_validate(seance).model_dump(mode="json"),
                "exercices": main._enrichir_noms_exercices_prevus(list(seance.exercices or []), db),
            }
            if seance
            else None
        ),
        historique_recent=coach_actions.get_historique(db, today).get("seances") or [],
        contextes_signales=coach_actions.get_contexte_signale(db, today).get("contraintes") or [],
        aujourdhui=today,
    )


def _messages_historique(db: Session) -> list[dict[str, str]]:
    messages = (
        db.query(models.MessageConversation)
        .order_by(models.MessageConversation.id.desc())
        .limit(MAX_MESSAGES_HISTORIQUE)
        .all()
    )
    return [
        {"role": "user" if m.role == "utilisateur" else "assistant", "content": m.contenu}
        for m in reversed(messages)
    ]


def _appel_mistral(messages: list[dict], tools: list[dict]) -> dict:
    return mistral_client.appeler_mistral_outils(messages, tools=tools)


def _arguments_de(appel: dict) -> dict[str, Any]:
    """Arguments d'un tool call, que le modèle les donne en JSON encodé ou en objet.

    Un JSON malformé n'est pas une raison de tomber : il devient un dict vide, et l'action
    répondra qu'il lui manque des informations — exactement comme pour un utilisateur trop vague.
    """
    bruts = (appel.get("function") or {}).get("arguments")
    if isinstance(bruts, dict):
        return bruts
    if not bruts:
        return {}
    try:
        charges = json.loads(bruts)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Arguments de tool call illisibles : %r", bruts)
        return {}
    return charges if isinstance(charges, dict) else {}


def repondre(
    db: Session,
    today: date,
    message_utilisateur: str,
    appel_llm: Optional[Callable[[list[dict], list[dict]], dict]] = None,
) -> dict[str, Any]:
    """Traite un message et renvoie ``{reponse, actions, contexte}``.

    Persiste le message utilisateur et la réponse du coach (mémoire d'expérience), mais tout
    fait métier a déjà été écrit par les actions elles-mêmes : purger la conversation ne fait
    rien perdre au moteur.

    Une panne du modèle n'est jamais silencieuse ni maquillée en réponse de coach : elle
    remonte en exception à l'appelant (l'endpoint la traduit en 502), de la même façon que la
    génération de séance et de programme le font déjà.
    """
    appel_llm = appel_llm or _appel_mistral

    contexte = construire_contexte(db, today)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT.format(contexte=coach_contexte.formater_pour_prompt(contexte))}
    ]
    messages.extend(_messages_historique(db))
    messages.append({"role": "user", "content": message_utilisateur})

    db.add(
        models.MessageConversation(
            role="utilisateur", contenu=message_utilisateur, actions=None, date=today
        )
    )
    db.commit()

    actions_effectuees: list[dict[str, Any]] = []
    reponse_texte = ""

    for tour in range(MAX_TOURS):
        message_llm = appel_llm(messages, OUTILS)
        appels = message_llm.get("tool_calls") or []
        reponse_texte = (message_llm.get("content") or "").strip()

        if not appels:
            break

        # Le message de l'assistant (avec ses tool_calls) doit être réinjecté tel quel avant
        # les résultats, sinon le modèle perd la trace de ce qu'il a demandé.
        messages.append(message_llm)

        for appel in appels:
            nom = (appel.get("function") or {}).get("name") or ""
            arguments = _arguments_de(appel)
            resultat = coach_actions.executer(nom, arguments, db, today)
            actions_effectuees.append({"nom": nom, "arguments": arguments, "resultat": resultat})
            messages.append(
                {
                    "role": "tool",
                    "name": nom,
                    "tool_call_id": appel.get("id", ""),
                    "content": json.dumps(resultat, ensure_ascii=False, default=str),
                }
            )
    else:
        logger.warning("Coach : %s tours d'outils atteints sans réponse finale.", MAX_TOURS)

    if not reponse_texte:
        # Le modèle a enchaîné des actions sans conclure (ou a atteint MAX_TOURS). On ne
        # fabrique pas une réponse de coach à sa place : on dit ce qui a été fait, factuellement.
        reponse_texte = _resume_factuel(actions_effectuees)

    db.add(
        models.MessageConversation(
            role="coach",
            contenu=reponse_texte,
            actions=[{"nom": a["nom"], "arguments": a["arguments"]} for a in actions_effectuees],
            date=today,
        )
    )
    db.commit()

    return {
        "reponse": reponse_texte,
        "actions": actions_effectuees,
        "contexte": construire_contexte(db, today),
    }


def _resume_factuel(actions: list[dict[str, Any]]) -> str:
    if not actions:
        return "Je n'ai pas de réponse à te donner sur ce point."
    reussies = [a["nom"] for a in actions if (a.get("resultat") or {}).get("ok")]
    if reussies:
        return "C'est fait : " + ", ".join(sorted(set(reussies))) + "."
    premier = actions[0].get("resultat") or {}
    return (
        premier.get("clarification_requise")
        or premier.get("erreur")
        or "Je n'ai pas réussi à traiter cette demande."
    )
