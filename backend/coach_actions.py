"""Couche d'actions métier du coach conversationnel (spécification V0 section 20).

C'est la frontière entre le langage et le moteur. Le LLM n'écrit jamais en base et ne décide
jamais d'une charge, d'un volume ou d'un planning : il choisit une action de ce module, avec
des arguments, et ce module délègue aux briques existantes (``main.py``, ``regles_seance``,
``moteur_decision``, ``adaptation_seance``, ``substitution``, ``duree_seance``). Le résultat
renvoyé est du JSON que le LLM n'a plus qu'à formuler en français.

Trois invariants tenus ici, pas dans le prompt (un prompt se contourne, pas un `if`) :

1. **Aucune invention.** Une action qui reçoit une information insuffisante ne complète pas :
   elle renvoie ``{"ok": False, "clarification_requise": "..."}``. Enregistrer une
   performance sans séries ni répétitions est impossible par construction
   (``enregistrer_performance``), et un nom d'exercice ambigu renvoie la liste des candidats
   plutôt qu'un choix arbitraire (``chercher_exercice``).
2. **Rien d'important ne reste dans la conversation.** Chaque fait déclaré est écrit dans les
   structures existantes : performances -> ``SerieLoggee`` puis ``HistoriqueSeance`` via
   l'endpoint de fin de séance ; douleur/fatigue -> ``ContexteSignale`` ; match déplacé ->
   ``Profil.calendrier_matchs``, qui déclenche le recalcul du programme.
3. **L'historique n'est jamais réécrit.** Aucune action ne touche une séance terminée ni une
   entrée d'historique : elles refusent explicitement (voir ``SeanceTermineeError``).

Import de ``main`` : volontairement tardif (``_main()``), parce que ``main`` importe ce
module. Le cycle est ainsi rompu sans dupliquer une seule ligne de logique d'endpoint.
"""

import logging
import unicodedata
from datetime import date, timedelta
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

import adaptation_seance
import models
import schemas
import substitution

logger = logging.getLogger("level.coach")

# Séances passées remontées par défaut à get_historique : de quoi parler de la semaine
# écoulée. Le coach peut en demander plus explicitement (argument `limite`).
LIMITE_HISTORIQUE_DEFAUT = 5
LIMITE_HISTORIQUE_MAX = 30

# Nombre maximal d'alternatives proposées quand un exercice devient impossible. Au-delà de 3,
# on ne propose plus, on noie (spécification V0 section 15 : « proposer 1 à 3 alternatives »).
MAX_ALTERNATIVES_PROPOSEES = 3

# Score minimal pour considérer qu'un nom d'exercice libre désigne bien un exercice de la
# bibliothèque, et écart minimal avec le suivant pour trancher sans demander confirmation.
# Volontairement strict : mieux vaut poser une question courte que loguer sur le mauvais
# exercice (une performance mal attribuée fausse ensuite toute la progression).
SCORE_MIN_CORRESPONDANCE = 0.5
ECART_MIN_POUR_TRANCHER = 0.15

DIFFICULTES_VALIDES = ("facile", "comme_prevu", "dur")


class ActionError(Exception):
    """Refus métier explicable, à relayer tel quel à l'utilisateur."""


class SeanceTermineeError(ActionError):
    """Tentative de modification d'une séance déjà terminée (historique figé)."""


def _main():
    """Import tardif de main.py (voir docstring du module : rupture du cycle d'import)."""
    import main

    return main


# ---------------------------------------------------------------------------
# Résolution d'un nom d'exercice libre -> exercice de la bibliothèque
# ---------------------------------------------------------------------------


def _normaliser(texte: str) -> str:
    sans_accents = "".join(
        c for c in unicodedata.normalize("NFD", texte or "") if unicodedata.category(c) != "Mn"
    )
    return "".join(c if c.isalnum() else " " for c in sans_accents.lower())


def _mots(texte: str) -> list[str]:
    # Mots de 2 lettres ou moins ignorés ("de", "au", "à") : ils n'apportent rien au matching
    # et feraient remonter des faux positifs sur des noms courts.
    return [m for m in _normaliser(texte).split() if len(m) > 2]


def _score_correspondance(recherche: str, nom_exercice: str) -> float:
    """Score 0..1 entre un nom libre et un nom de la bibliothèque.

    Déterministe et sans dépendance externe : proportion des mots de la recherche retrouvés
    dans le nom de l'exercice (préfixe accepté, pour « développé » vs « développés »), avec
    un bonus quand le nom complet est contenu tel quel. Ce n'est pas de la sémantique — c'est
    justement le but : pas de correspondance devinée, le cas ambigu remonte à l'utilisateur.
    """
    mots_recherche = _mots(recherche)
    if not mots_recherche:
        return 0.0
    mots_exercice = _mots(nom_exercice)
    if not mots_exercice:
        return 0.0

    trouves = sum(
        1
        for mot in mots_recherche
        if any(cible.startswith(mot) or mot.startswith(cible) for cible in mots_exercice)
    )
    score = trouves / len(mots_recherche)

    if _normaliser(recherche).strip() in _normaliser(nom_exercice):
        score = min(1.0, score + 0.2)
    # Pénalise un nom de bibliothèque beaucoup plus long que la recherche : « développé »
    # seul ne doit pas matcher « développé incliné haltères unilatéral » aussi bien que
    # « développé couché ».
    if len(mots_exercice) > len(mots_recherche):
        score *= len(mots_recherche) / len(mots_exercice) * 0.5 + 0.5
    return round(score, 4)


def chercher_exercice(db: Session, today: date, nom: str = "", **_) -> dict[str, Any]:
    """Traduit un nom d'exercice dit en langage naturel en exercice de la bibliothèque.

    Action à part entière (et pas un détail d'implémentation) parce que c'est le point exact
    où le coach pourrait inventer : sans elle, un LLM enverrait un ``exercice_id`` plausible.
    Ici, soit la correspondance est nette et on renvoie l'exercice, soit elle ne l'est pas et
    on renvoie les candidats pour que la question soit posée à l'utilisateur.
    """
    if not (nom or "").strip():
        return {"ok": False, "clarification_requise": "De quel exercice s'agit-il ?"}

    exercices = db.query(models.ExerciceBibliotheque).all()
    if not exercices:
        return {"ok": False, "erreur": "La bibliothèque d'exercices est vide."}

    scores = sorted(
        ((_score_correspondance(nom, ex.nom), ex) for ex in exercices),
        key=lambda t: (-t[0], t[1].nom),
    )
    meilleur_score, meilleur = scores[0]
    second_score = scores[1][0] if len(scores) > 1 else 0.0

    if meilleur_score < SCORE_MIN_CORRESPONDANCE:
        return {
            "ok": False,
            "trouve": False,
            "clarification_requise": (
                f"Aucun exercice de la bibliothèque ne correspond à « {nom} ». "
                "Demande à l'utilisateur de préciser le nom."
            ),
            "suggestions": [
                {"exercice_id": ex.id, "nom": ex.nom} for score, ex in scores[:MAX_ALTERNATIVES_PROPOSEES] if score > 0
            ],
        }

    if meilleur_score - second_score < ECART_MIN_POUR_TRANCHER:
        candidats = [
            {"exercice_id": ex.id, "nom": ex.nom}
            for score, ex in scores[:MAX_ALTERNATIVES_PROPOSEES]
            if score >= SCORE_MIN_CORRESPONDANCE
        ]
        return {
            "ok": False,
            "trouve": False,
            "ambigu": True,
            "clarification_requise": f"« {nom} » peut désigner plusieurs exercices : demande lequel.",
            "choix_possibles": candidats,
        }

    return {
        "ok": True,
        "trouve": True,
        "exercice_id": meilleur.id,
        "nom": meilleur.nom,
        "groupe_musculaire": meilleur.groupe_musculaire,
        "score": meilleur_score,
    }


def _resoudre_exercice(
    db: Session, exercice_id: Optional[int], nom: Optional[str]
) -> tuple[Optional[models.ExerciceBibliotheque], Optional[dict[str, Any]]]:
    """(exercice, refus) — le refus, s'il existe, est déjà formulé pour l'utilisateur."""
    if exercice_id is not None:
        exercice = db.get(models.ExerciceBibliotheque, exercice_id)
        if exercice is None:
            return None, {"ok": False, "erreur": f"Aucun exercice #{exercice_id} dans la bibliothèque."}
        return exercice, None

    resultat = chercher_exercice(db, date.today(), nom=nom or "")
    if not resultat.get("ok"):
        return None, resultat
    return db.get(models.ExerciceBibliotheque, resultat["exercice_id"]), None


# ---------------------------------------------------------------------------
# Lecture : profil, programme, jour, historique, progression
# ---------------------------------------------------------------------------


def _profil_dict(db: Session) -> Optional[dict[str, Any]]:
    profil = db.query(models.Profil).order_by(models.Profil.id.desc()).first()
    return schemas.ProfilOut.model_validate(profil).model_dump(mode="json") if profil else None


def get_profil(db: Session, today: date, **_) -> dict[str, Any]:
    profil = _profil_dict(db)
    if profil is None:
        return {"ok": False, "erreur": "Aucun profil enregistré : l'onboarding n'est pas terminé."}
    return {"ok": True, "profil": profil}


def get_programme(db: Session, today: date, **_) -> dict[str, Any]:
    programme = _main().get_programme_actif(db=db)
    if programme is None:
        return {"ok": False, "erreur": "Aucun programme actif. Il faut le générer (action generer_programme)."}
    return {"ok": True, "programme": schemas.ProgrammeOut.model_validate(programme).model_dump(mode="json")}


def generer_programme(db: Session, today: date, regenerer: bool = False, **_) -> dict[str, Any]:
    """Construit (ou reconstruit) le programme avec le moteur existant, et l'enregistre.

    Délègue intégralement à ``POST /api/programme/generer`` : structure hebdomadaire
    déterministe (``moteur_decision.construire_structure_hebdomadaire``) puis détail par
    Mistral cadré et revalidé. Le LLM du coach n'écrit pas un programme, il déclenche celui
    du moteur — et le programme est persisté, jamais seulement affiché dans le chat.
    """
    main = _main()
    try:
        programme = main.generer_programme(
            schemas.ProgrammeGenererPayload(regenerer=bool(regenerer)), db=db, today=today
        )
    except main.HTTPException as exc:  # profil manquant, etc. : refus métier lisible
        return {"ok": False, "erreur": str(exc.detail)}
    return {
        "ok": True,
        "programme": schemas.ProgrammeOut.model_validate(programme).model_dump(mode="json"),
        "enregistre": True,
    }


def _seance_du_jour(db: Session, today: date) -> Optional[models.Seance]:
    return db.query(models.Seance).filter(models.Seance.date == today).order_by(models.Seance.id).first()


def _seance_payload(db: Session, seance: models.Seance) -> dict[str, Any]:
    main = _main()
    exercices = main._enrichir_noms_exercices_prevus(list(seance.exercices or []), db)
    return {
        "seance_id": seance.id,
        "nom": seance.nom,
        "statut": seance.statut,
        "type_seance": seance.type_seance,
        "duree_prevue_min": seance.duree_prevue,
        "explication": seance.explication,
        "exercices": exercices,
    }


def get_seance_du_jour(db: Session, today: date, generer: bool = True, **_) -> dict[str, Any]:
    """La séance prévue aujourd'hui, générée par le moteur si elle n'existe pas encore.

    Ne fabrique jamais de séance côté coach : si aucune séance n'existe, on appelle
    ``/api/seance/generer``, qui applique le gabarit du programme, le moteur de règles
    calendaire et les garde-fous. Un refus du moteur (jour de match, jour de repos) est
    renvoyé tel quel — c'est une décision, pas une erreur à contourner.
    """
    main = _main()
    contexte = main.get_contexte_jour(db=db, today=today)

    seance = _seance_du_jour(db, today)
    if seance is not None:
        return {"ok": True, "contexte_jour": contexte, "seance": _seance_payload(db, seance)}

    if not generer:
        return {"ok": True, "contexte_jour": contexte, "seance": None}

    try:
        main.generer_seance(schemas.EtatDuJour(), db=db, today=today)
    except main.HTTPException as exc:
        # 409 = décision du moteur (match, repos programmé). On la remonte comme telle, avec
        # le motif, pour que le coach l'explique au lieu de générer une séance quand même.
        return {
            "ok": False,
            "contexte_jour": contexte,
            "seance": None,
            "refus_moteur": str(exc.detail),
            "statut_jour": contexte.get("statut"),
        }
    except Exception as exc:  # génération indisponible (Mistral, bibliothèque vide...)
        logger.exception("Génération de la séance du jour impossible depuis le coach")
        return {"ok": False, "contexte_jour": contexte, "seance": None, "erreur": str(exc)}

    seance = _seance_du_jour(db, today)
    return {
        "ok": seance is not None,
        "contexte_jour": contexte,
        "seance": _seance_payload(db, seance) if seance else None,
    }


def get_contexte_jour(db: Session, today: date, **_) -> dict[str, Any]:
    return {"ok": True, "contexte_jour": _main().get_contexte_jour(db=db, today=today)}


def get_historique(db: Session, today: date, limite: int = LIMITE_HISTORIQUE_DEFAUT, **_) -> dict[str, Any]:
    limite = max(1, min(int(limite or LIMITE_HISTORIQUE_DEFAUT), LIMITE_HISTORIQUE_MAX))
    entries = (
        db.query(models.HistoriqueSeance)
        .order_by(models.HistoriqueSeance.date.desc(), models.HistoriqueSeance.id.desc())
        .limit(limite)
        .all()
    )
    return {
        "ok": True,
        "seances": [
            {
                "date": e.date.isoformat(),
                "type_seance": e.type_seance,
                "rpe": e.rpe,
                "pourcentage_complete": e.pourcentage_complete,
                "zone_sensible_signalee": e.zone_sensible_signalee,
                "exercices_realises": e.exercices_realises or [],
            }
            for e in entries
        ],
    }


def get_progression_exercice(
    db: Session, today: date, exercice_id: Optional[int] = None, nom: Optional[str] = None, **_
) -> dict[str, Any]:
    """Progression réelle sur un exercice, séance par séance.

    Lue depuis ``SerieLoggee`` (ce qui a été coché pendant les séances terminées), donc à
    partir de ce que l'utilisateur a réellement fait. Une absence de données reste une
    absence de données : la réponse porte ``assez_de_donnees: False`` plutôt qu'une tendance
    fabriquée (spécification V0 section 17 : ne pas générer de statistiques fictives).
    """
    exercice, refus = _resoudre_exercice(db, exercice_id, nom)
    if refus is not None:
        return refus

    lignes = (
        db.query(models.SerieLoggee, models.Seance.date)
        .join(models.Seance, models.Seance.id == models.SerieLoggee.seance_id)
        .filter(
            models.SerieLoggee.exercice_id == exercice.id,
            models.SerieLoggee.coche == 1,
            models.Seance.statut == "terminee",
        )
        .order_by(models.Seance.date.asc(), models.SerieLoggee.numero_serie.asc())
        .all()
    )

    par_date: dict[str, list[dict[str, Any]]] = {}
    for serie, jour in lignes:
        par_date.setdefault(jour.isoformat(), []).append(
            {"poids_kg": serie.poids_kg, "repetitions": serie.repetitions, "rpe_approx": serie.rpe_approx}
        )

    seances = [
        {
            "date": jour,
            "series": series,
            "charge_max_kg": max((s["poids_kg"] for s in series if s["poids_kg"] is not None), default=None),
            "reps_totales": sum(s["repetitions"] or 0 for s in series),
        }
        for jour, series in sorted(par_date.items())
    ]

    return {
        "ok": True,
        "exercice_id": exercice.id,
        "nom": exercice.nom,
        "assez_de_donnees": len(seances) >= 2,
        "nb_seances": len(seances),
        "seances": seances,
    }


def get_bilan(db: Session, today: date, jours: int = 7, **_) -> dict[str, Any]:
    bilan = _main().get_bilan_hebdomadaire(jours=int(jours or 7), db=db, today=today)
    return {"ok": True, "bilan": bilan.model_dump(mode="json") if hasattr(bilan, "model_dump") else bilan}


# ---------------------------------------------------------------------------
# Écriture : enregistrement d'une séance et de ses performances
# ---------------------------------------------------------------------------


def _assurer_seance_du_jour(db: Session, today: date) -> models.Seance:
    """Séance sur laquelle attacher une performance déclarée.

    Si aucune séance n'existe (utilisateur qui s'entraîne un jour non prévu, ou qui raconte
    sa séance sans l'avoir ouverte dans l'app), on en crée une vide plutôt que de refuser :
    ``exercices`` reste ``[]``, donc « prévu » reste honnêtement vide et le pourcentage de
    complétion ne sera pas calculé sur une cible inventée.
    """
    seance = _seance_du_jour(db, today)
    if seance is not None:
        return seance
    seance = models.Seance(
        date=today,
        nom="Séance libre",
        exercices=[],
        statut="planifiee",
        type_seance=None,
    )
    db.add(seance)
    db.commit()
    db.refresh(seance)
    return seance


def enregistrer_performance(
    db: Session,
    today: date,
    exercice_id: Optional[int] = None,
    nom: Optional[str] = None,
    series: Optional[int] = None,
    repetitions: Optional[int] = None,
    charge_kg: Optional[float] = None,
    difficulte: Optional[str] = None,
    **_,
) -> dict[str, Any]:
    """Transforme une performance racontée en ``SerieLoggee`` réelles.

    Exigences volontaires (spécification V0 section 9, « ne pas inventer les données ») :
    ``series`` et ``repetitions`` sont obligatoires. « J'ai fait du développé incliné lourd »
    ne peut donc PAS produire un enregistrement : l'action renvoie la question à poser. La
    charge, elle, reste optionnelle — beaucoup d'exercices se font au poids du corps.

    Idempotence (section 28, « pas de doublon en cas de double appel ») : deux appels
    identiques ne créent pas huit séries. Si les séries déjà loguées pour cet exercice dans
    cette séance correspondent exactement à ce qui est demandé, on ne réécrit rien. Si elles
    diffèrent, c'est une correction de l'utilisateur : les séries de CET exercice dans CETTE
    séance non terminée sont remplacées. Une séance terminée est refusée — son historique est
    figé.
    """
    if series is None or repetitions is None:
        manquant = []
        if series is None:
            manquant.append("le nombre de séries")
        if repetitions is None:
            manquant.append("le nombre de répétitions")
        return {
            "ok": False,
            "clarification_requise": (
                "Impossible d'enregistrer sans " + " et ".join(manquant) + ". Demande-les avant d'enregistrer."
            ),
        }

    try:
        series = int(series)
        repetitions = int(repetitions)
    except (TypeError, ValueError):
        return {"ok": False, "clarification_requise": "Séries et répétitions doivent être des nombres entiers."}

    if series < 1 or repetitions < 1:
        return {"ok": False, "clarification_requise": "Séries et répétitions doivent être au moins égales à 1."}

    if difficulte is not None and difficulte not in DIFFICULTES_VALIDES:
        difficulte = None  # valeur hors vocabulaire : ignorée plutôt que traduite au jugé

    exercice, refus = _resoudre_exercice(db, exercice_id, nom)
    if refus is not None:
        return refus

    seance = _assurer_seance_du_jour(db, today)
    if seance.statut == "terminee":
        raise SeanceTermineeError(
            "La séance d'aujourd'hui est déjà terminée : son historique ne peut plus être modifié."
        )

    existantes = (
        db.query(models.SerieLoggee)
        .filter(models.SerieLoggee.seance_id == seance.id, models.SerieLoggee.exercice_id == exercice.id)
        .order_by(models.SerieLoggee.numero_serie.asc())
        .all()
    )

    charge = float(charge_kg) if charge_kg is not None else None
    identique = (
        len(existantes) == series
        and all(
            s.repetitions == repetitions and s.poids_kg == charge and s.difficulte == difficulte
            for s in existantes
        )
    )
    if identique:
        return {
            "ok": True,
            "deja_enregistre": True,
            "seance_id": seance.id,
            "exercice_id": exercice.id,
            "nom": exercice.nom,
            "series": series,
            "repetitions": repetitions,
            "charge_kg": charge,
            "difficulte": difficulte,
        }

    for ancienne in existantes:
        db.delete(ancienne)
    db.commit()

    main = _main()
    creees = []
    for numero in range(1, series + 1):
        creees.append(
            main.create_serie_loggee(
                schemas.SerieLoggeeCreate(
                    seance_id=seance.id,
                    exercice_id=exercice.id,
                    numero_serie=numero,
                    poids_kg=charge,
                    repetitions=repetitions,
                    coche=True,
                    difficulte=difficulte,
                ),
                db=db,
            )
        )

    return {
        "ok": True,
        "corrige": bool(existantes),
        "seance_id": seance.id,
        "exercice_id": exercice.id,
        "nom": exercice.nom,
        "series": len(creees),
        "repetitions": repetitions,
        "charge_kg": charge,
        "difficulte": difficulte,
        "rpe_approx": creees[0].rpe_approx if creees else None,
    }


def terminer_seance(
    db: Session,
    today: date,
    seance_id: Optional[int] = None,
    note: Optional[str] = None,
    duree_reelle_min: Optional[int] = None,
    zone_sensible: Optional[str] = None,
    **_,
) -> dict[str, Any]:
    """Clôture la séance : écrit l'``HistoriqueSeance``, l'XP, le streak, le niveau observé.

    Délègue à ``POST /api/seance/terminer``, déjà idempotent (un second appel renvoie
    l'historique existant sans re-créditer l'XP). Le RPE n'est pas demandé au LLM : il est
    calculé par le backend à partir des validations réelles de chaque série.
    """
    main = _main()
    seance = db.get(models.Seance, seance_id) if seance_id else _seance_du_jour(db, today)
    if seance is None:
        return {"ok": False, "erreur": "Aucune séance à terminer aujourd'hui."}

    if zone_sensible is not None and zone_sensible not in main.ZONES_SENSIBLES_VALIDES:
        zone_sensible = None

    try:
        resultat = main.terminer_seance(
            schemas.TerminerSeancePayload(
                seance_id=seance.id,
                note=note,
                duree_reelle_min=duree_reelle_min,
                zone_sensible=zone_sensible,
            ),
            db=db,
        )
    except main.HTTPException as exc:
        return {"ok": False, "erreur": str(exc.detail)}

    resume = resultat.resume
    return {
        "ok": True,
        "seance_id": seance.id,
        "deja_terminee": bool(resume.get("deja_terminee")),
        "resume": resume,
        "xp_gagne": resultat.xp_gagne,
        "historique_id": resultat.historique_id,
    }


# ---------------------------------------------------------------------------
# Adaptation de la séance du jour
# ---------------------------------------------------------------------------


def _meta_exercices(db: Session, exercice_ids) -> dict[int, dict[str, Any]]:
    ids = [i for i in exercice_ids if i is not None]
    if not ids:
        return {}
    exercices = (
        db.query(models.ExerciceBibliotheque).filter(models.ExerciceBibliotheque.id.in_(ids)).all()
    )
    return {ex.id: substitution.exercice_vers_dict(ex) for ex in exercices}


def _tracer_adaptation(seance: models.Seance, motif: str, changements: list[str]) -> None:
    """Consigne l'adaptation dans ``Seance.decision_adaptation``, à côté de la recommandation
    initiale du moteur — donc reportée telle quelle dans l'historique par ``terminer_seance``.
    L'adaptation reste ainsi explicable après coup, au lieu de disparaître avec le chat."""
    decision = dict(seance.decision_adaptation or {})
    raisons = list(decision.get("raisons") or [])
    raisons.extend(changements)
    decision["raisons"] = raisons
    adaptations = list(decision.get("adaptations_coach") or [])
    adaptations.append({"motif": motif, "changements": changements})
    decision["adaptations_coach"] = adaptations
    seance.decision_adaptation = decision


def adapter_seance(
    db: Session,
    today: date,
    motif: str = "",
    minutes_disponibles: Optional[int] = None,
    materiel: Optional[str] = None,
    **_,
) -> dict[str, Any]:
    """Adapte la séance du jour à une contrainte, et enregistre le résultat.

    ``motif`` : ``duree`` (avec ``minutes_disponibles``), ``fatigue``, ou ``materiel`` (avec
    ``materiel``). La décision de ce qu'on coupe appartient à ``adaptation_seance`` ; ici on
    persiste, on trace, et on renvoie la séance adaptée. Rien n'est « annoncé » sans être
    écrit (spécification V0 section 13).
    """
    seance = _seance_du_jour(db, today)
    if seance is None:
        return {"ok": False, "erreur": "Aucune séance générée aujourd'hui : il n'y a rien à adapter."}
    if seance.statut == "terminee":
        raise SeanceTermineeError("La séance d'aujourd'hui est déjà terminée : elle ne peut plus être adaptée.")

    items = [item for item in (seance.exercices or []) if isinstance(item, dict)]
    if not items:
        return {"ok": False, "erreur": "La séance du jour ne contient aucun exercice à adapter."}

    meta = _meta_exercices(db, [item.get("exercice_id") for item in items])

    if motif == "duree":
        if minutes_disponibles is None:
            return {"ok": False, "clarification_requise": "Combien de minutes sont disponibles aujourd'hui ?"}
        resultat = adaptation_seance.adapter_pour_duree(items, meta, int(minutes_disponibles))
    elif motif == "fatigue":
        resultat = adaptation_seance.adapter_pour_fatigue(items, meta)
    elif motif == "materiel":
        if not materiel:
            return {
                "ok": False,
                "clarification_requise": "Quel matériel est disponible aujourd'hui ?",
                "materiels_connus": sorted(substitution.MATERIEL_ONBOARDING_VERS_TAGS),
            }
        return _adapter_materiel(db, today, seance, items, meta, materiel)
    else:
        return {
            "ok": False,
            "erreur": f"Motif d'adaptation inconnu : {motif!r}. Attendu : duree, fatigue ou materiel.",
        }

    seance.exercices = resultat["exercices"]
    seance.duree_prevue = resultat["duree_apres_min"]
    _tracer_adaptation(seance, motif, resultat["changements"])
    db.commit()
    db.refresh(seance)

    return {
        "ok": True,
        "motif": motif,
        "seance": _seance_payload(db, seance),
        "duree_avant_min": resultat["duree_avant_min"],
        "duree_apres_min": resultat["duree_apres_min"],
        "changements": resultat["changements"],
        "enregistre": True,
    }


def _adapter_materiel(
    db: Session,
    today: date,
    seance: models.Seance,
    items: list[dict[str, Any]],
    meta: dict[int, dict[str, Any]],
    materiel: str,
) -> dict[str, Any]:
    """Remplace les exercices que le matériel du jour ne permet plus.

    Chaque remplacement passe par ``substitution.trouver_alternatives`` (la bibliothèque de
    substitutions existante, qui raisonne pattern de mouvement et groupe musculaire) puis par
    l'endpoint de remplacement, qui conserve la chaîne A -> B. Quand aucune alternative
    n'existe, on ne bricole pas : on le dit.
    """
    main = _main()
    incompatibles = adaptation_seance.exercices_incompatibles_materiel(items, meta, materiel)
    if not incompatibles:
        return {
            "ok": True,
            "motif": "materiel",
            "seance": _seance_payload(db, seance),
            "changements": [f"Tous les exercices prévus sont réalisables avec : {materiel}."],
            "enregistre": False,
        }

    bibliotheque = db.query(models.ExerciceBibliotheque).all()
    bibliotheque_dicts = [substitution.exercice_vers_dict(ex) for ex in bibliotheque]

    changements: list[str] = []
    sans_alternative: list[str] = []
    for exercice_id in incompatibles:
        actuel = db.get(models.ExerciceBibliotheque, exercice_id)
        if actuel is None:
            continue
        deja_presents = {
            item.get("exercice_id") for item in (seance.exercices or []) if isinstance(item, dict)
        }
        _, zones_sensibles = main._materiel_et_zones_pour_seance(seance, db)
        candidats = substitution.trouver_alternatives(
            substitution.exercice_vers_dict(actuel),
            bibliotheque_dicts,
            deja_presents,
            materiel,
            zones_sensibles,
        )
        if not candidats:
            sans_alternative.append(actuel.nom)
            continue
        remplacant_id = candidats[0]["exercice"]["id"]
        main.remplacer_exercice(
            seance.id,
            schemas.RemplacerExercicePayload(
                exercice_id_actuel=exercice_id, exercice_id_nouveau=remplacant_id
            ),
            db=db,
        )
        remplacant = db.get(models.ExerciceBibliotheque, remplacant_id)
        changements.append(
            f"{actuel.nom} remplacé par {remplacant.nom} (même objectif, réalisable avec : {materiel})."
        )

    if sans_alternative:
        changements.append(
            "Aucune alternative pertinente dans la bibliothèque pour : "
            + ", ".join(sans_alternative)
            + ". Ces exercices restent tels quels."
        )

    if changements:
        _tracer_adaptation(seance, "materiel", changements)
        db.commit()
    db.refresh(seance)

    return {
        "ok": True,
        "motif": "materiel",
        "seance": _seance_payload(db, seance),
        "changements": changements,
        "exercices_sans_alternative": sans_alternative,
        "enregistre": True,
    }


def proposer_alternatives(
    db: Session, today: date, exercice_id: Optional[int] = None, nom: Optional[str] = None, **_
) -> dict[str, Any]:
    """1 à 3 alternatives à un exercice de la séance du jour, sans rien appliquer.

    Sert le cas « je ne peux pas faire cet exercice » (section 15) : le coach propose, et
    c'est ``remplacer_exercice`` qui applique une fois le choix fait.
    """
    seance = _seance_du_jour(db, today)
    if seance is None:
        return {"ok": False, "erreur": "Aucune séance générée aujourd'hui."}

    exercice, refus = _resoudre_exercice(db, exercice_id, nom)
    if refus is not None:
        return refus

    main = _main()
    try:
        resultat = main.get_alternatives_exercice(seance.id, exercice.id, db=db)
    except main.HTTPException as exc:
        return {"ok": False, "erreur": str(exc.detail)}

    alternatives = [
        {"exercice_id": a.exercice.id, "nom": a.exercice.nom, "memes_criteres": a.memes_criteres}
        for a in resultat.alternatives[:MAX_ALTERNATIVES_PROPOSEES]
    ]
    return {
        "ok": True,
        "seance_id": seance.id,
        "exercice_actuel": {"exercice_id": exercice.id, "nom": exercice.nom},
        "alternatives": alternatives,
        "aucune_alternative": not alternatives,
    }


def remplacer_exercice(
    db: Session,
    today: date,
    exercice_id_actuel: Optional[int] = None,
    nom_actuel: Optional[str] = None,
    exercice_id_nouveau: Optional[int] = None,
    nom_nouveau: Optional[str] = None,
    **_,
) -> dict[str, Any]:
    """Applique un remplacement dans la séance du jour, via l'endpoint existant.

    Les séries déjà réalisées sur l'ancien exercice restent en base et restent rattachées au
    même slot (``historique_exercice_ids``) : remplacer un exercice n'efface jamais ce qui a
    déjà été fait.
    """
    seance = _seance_du_jour(db, today)
    if seance is None:
        return {"ok": False, "erreur": "Aucune séance générée aujourd'hui."}

    actuel, refus = _resoudre_exercice(db, exercice_id_actuel, nom_actuel)
    if refus is not None:
        return refus
    nouveau, refus = _resoudre_exercice(db, exercice_id_nouveau, nom_nouveau)
    if refus is not None:
        return refus

    main = _main()
    try:
        resultat = main.remplacer_exercice(
            seance.id,
            schemas.RemplacerExercicePayload(
                exercice_id_actuel=actuel.id, exercice_id_nouveau=nouveau.id
            ),
            db=db,
        )
    except main.HTTPException as exc:
        return {"ok": False, "erreur": str(exc.detail)}

    return {
        "ok": True,
        "remplace": {"avant": actuel.nom, "apres": nouveau.nom},
        "series_deja_realisees": resultat.series_deja_realisees,
        "message_confirmation": resultat.message_confirmation,
        "seance": _seance_payload(db, seance),
        "enregistre": True,
    }


# ---------------------------------------------------------------------------
# Contexte déclaré : douleur, fatigue, contraintes
# ---------------------------------------------------------------------------


def _contextes_actifs(db: Session, today: date) -> list[models.ContexteSignale]:
    return (
        db.query(models.ContexteSignale)
        .filter(
            models.ContexteSignale.date_debut <= today,
            (models.ContexteSignale.date_fin.is_(None)) | (models.ContexteSignale.date_fin >= today),
        )
        .order_by(models.ContexteSignale.date_debut.desc())
        .all()
    )


def signaler_douleur(
    db: Session,
    today: date,
    zone: Optional[str] = None,
    details: Optional[str] = None,
    persistante: bool = False,
    **_,
) -> dict[str, Any]:
    """Enregistre une douleur signalée et sort la zone concernée des séances à venir.

    Cas de sécurité (spécification V0 section 16). Ce module ne qualifie jamais la douleur :
    il enregistre ce qui a été dit (``details`` tel quel), borne la zone dans le temps sur la
    même fenêtre que le garde-fou existant (``JOURS_VALIDITE_ZONE_SENSIBLE``), et renvoie un
    drapeau ``orienter_vers_professionnel`` quand la douleur est déclarée persistante. Aucune
    cause, aucun diagnostic, aucune durée de guérison n'est produit ici — et le prompt du
    coach interdit d'en formuler.
    """
    main = _main()
    zones_valides = main.ZONES_SENSIBLES_VALIDES
    if zone not in zones_valides:
        return {
            "ok": False,
            "clarification_requise": (
                "Précise la zone concernée pour que LEVEL puisse l'exclure des prochaines séances."
            ),
            "zones_possibles": list(zones_valides),
        }

    fin = today + timedelta(days=main.JOURS_VALIDITE_ZONE_SENSIBLE)
    signal = models.ContexteSignale(
        type="douleur", valeur=zone, details=details, date_debut=today, date_fin=fin
    )
    db.add(signal)

    # La zone est aussi inscrite sur l'historique de la dernière séance terminée quand la
    # douleur est apparue pendant celle-ci : c'est ce champ que lit le garde-fou existant
    # (regles_seance.appliquer_garde_fous via _construire_contexte_historique), donc sans ça
    # la douleur déclarée dans le chat n'influencerait aucune génération.
    dernier = (
        db.query(models.HistoriqueSeance)
        .order_by(models.HistoriqueSeance.date.desc(), models.HistoriqueSeance.id.desc())
        .first()
    )
    inscrite_sur_historique = False
    if dernier is not None and (today - dernier.date).days <= main.JOURS_VALIDITE_ZONE_SENSIBLE:
        if not dernier.zone_sensible_signalee:
            dernier.zone_sensible_signalee = zone
            inscrite_sur_historique = True
    db.commit()

    # Exercices de la séance du jour touchant cette zone : le coach doit pouvoir arrêter
    # l'exercice concerné tout de suite, pas seulement « pour la prochaine fois ».
    seance = _seance_du_jour(db, today)
    exercices_concernes = []
    if seance is not None and seance.statut != "terminee":
        for item in seance.exercices or []:
            if not isinstance(item, dict):
                continue
            exercice = db.get(models.ExerciceBibliotheque, item.get("exercice_id"))
            if exercice and substitution.groupe_concerne_par_zone_sensible(
                exercice.groupe_musculaire, [zone]
            ):
                exercices_concernes.append({"exercice_id": exercice.id, "nom": exercice.nom})

    return {
        "ok": True,
        "zone": zone,
        "enregistre": True,
        "exclue_jusqu_au": fin.isoformat(),
        "inscrite_sur_derniere_seance": inscrite_sur_historique,
        "exercices_concernes_aujourdhui": exercices_concernes,
        "orienter_vers_professionnel": bool(persistante),
        "consigne_securite": (
            "Ne jamais nommer de cause ni de diagnostic. Proposer d'arrêter l'exercice concerné et "
            "une adaptation prudente. Si la douleur est persistante, importante ou inquiétante, "
            "recommander de consulter un professionnel de santé."
        ),
    }


def signaler_fatigue(
    db: Session, today: date, details: Optional[str] = None, adapter: bool = True, **_
) -> dict[str, Any]:
    """Enregistre une fatigue déclarée et allège la séance du jour si elle existe."""
    signal = models.ContexteSignale(
        type="fatigue", valeur=None, details=details, date_debut=today, date_fin=today
    )
    db.add(signal)
    db.commit()

    resultat_adaptation = None
    if adapter and _seance_du_jour(db, today) is not None:
        resultat_adaptation = adapter_seance(db, today, motif="fatigue")

    return {"ok": True, "enregistre": True, "adaptation": resultat_adaptation}


def get_contexte_signale(db: Session, today: date, **_) -> dict[str, Any]:
    return {
        "ok": True,
        "contraintes": [
            {
                "type": c.type,
                "valeur": c.valeur,
                "details": c.details,
                "date_debut": c.date_debut.isoformat(),
                "date_fin": c.date_fin.isoformat() if c.date_fin else None,
            }
            for c in _contextes_actifs(db, today)
        ],
    }


# ---------------------------------------------------------------------------
# Modification du cadre : matchs, disponibilités, matériel
# ---------------------------------------------------------------------------


def _patch_profil(db: Session, today: date, patch: schemas.ProfilPatch) -> dict[str, Any]:
    main = _main()
    try:
        resultat = main.patch_profil(patch, db=db, today=today)
    except main.HTTPException as exc:
        return {"ok": False, "erreur": str(exc.detail)}
    return {
        "ok": True,
        "programme_recalcule": resultat.programme_recalcule,
        "programme_erreur": resultat.programme_erreur,
        "seance_du_jour_supprimee": resultat.seance_du_jour_supprimee,
        "profil": resultat.profil.model_dump(mode="json"),
    }


def deplacer_match(
    db: Session,
    today: date,
    nouvelle_date: Optional[str] = None,
    date_annulee: Optional[str] = None,
    jour_habituel: Optional[str] = None,
    **_,
) -> dict[str, Any]:
    """Met à jour le calendrier de matchs, puis laisse le moteur réévaluer la semaine.

    Trois usages, combinables : déplacer un match (``nouvelle_date`` + ``date_annulee``),
    ajouter un match ponctuel (``nouvelle_date`` seule), changer le jour habituel
    (``jour_habituel``). La réorganisation de la semaine n'est pas décidée ici : le PATCH du
    profil reconstruit le programme via ``moteur_decision.construire_structure_hebdomadaire``,
    qui replace les séances autour du match.
    """
    profil = _profil_dict(db)
    if profil is None:
        return {"ok": False, "erreur": "Aucun profil enregistré."}

    calendrier = dict(profil.get("calendrier_matchs") or {})
    exceptions = list(calendrier.get("exceptions") or [])
    annulations = list(calendrier.get("annulations") or [])

    if not (nouvelle_date or date_annulee or jour_habituel):
        return {
            "ok": False,
            "clarification_requise": "Quelle date de match change, et pour quelle nouvelle date ?",
        }

    try:
        if date_annulee:
            iso = date.fromisoformat(date_annulee).isoformat()
            if iso not in annulations:
                annulations.append(iso)
            # Une exception précédemment ajoutée sur cette date est retirée : sans ça, la date
            # resterait un match malgré l'annulation.
            exceptions = [e for e in exceptions if str(e.get("date")) != iso]
        if nouvelle_date:
            iso = date.fromisoformat(nouvelle_date).isoformat()
            if all(str(e.get("date")) != iso for e in exceptions):
                exceptions.append({"date": iso, "label": "Match déplacé"})
            annulations = [a for a in annulations if str(a) != iso]
    except ValueError:
        return {"ok": False, "clarification_requise": "Les dates doivent être au format AAAA-MM-JJ."}

    calendrier["exceptions"] = exceptions
    calendrier["annulations"] = annulations
    if jour_habituel:
        calendrier["jour_habituel"] = jour_habituel

    resultat = _patch_profil(
        db, today, schemas.ProfilPatch(calendrier_matchs=schemas.CalendrierMatchs(**calendrier))
    )
    if resultat.get("ok"):
        resultat["calendrier_matchs"] = calendrier
        resultat["contexte_jour"] = _main().get_contexte_jour(db=db, today=today)
    return resultat


def mettre_a_jour_disponibilites(
    db: Session, today: date, disponibilites: Optional[dict[str, Any]] = None, **_
) -> dict[str, Any]:
    """Change les jours/minutes disponibles, ce qui reconstruit le programme.

    ``disponibilites`` : dict partiel ``{"jeudi": null, "vendredi": 60}`` fusionné avec
    l'existant (les jours non cités ne changent pas), en minuscules sans accent comme
    ``user_model_v2.JOURS_DISPONIBILITES``. ``null`` = jour indisponible.
    """
    if not disponibilites:
        return {"ok": False, "clarification_requise": "Quels jours changent, et pour combien de minutes ?"}

    profil = _profil_dict(db)
    if profil is None:
        return {"ok": False, "erreur": "Aucun profil enregistré."}

    import user_model_v2

    fusionnees = dict(profil.get("disponibilites") or {})
    inconnus = [j for j in disponibilites if j not in user_model_v2.JOURS_DISPONIBILITES]
    if inconnus:
        return {
            "ok": False,
            "clarification_requise": f"Jours non reconnus : {inconnus}.",
            "jours_attendus": list(user_model_v2.JOURS_DISPONIBILITES),
        }
    fusionnees.update(disponibilites)

    resultat = _patch_profil(db, today, schemas.ProfilPatch(disponibilites=fusionnees))
    if resultat.get("ok"):
        resultat["disponibilites"] = fusionnees
        resultat["contexte_jour"] = _main().get_contexte_jour(db=db, today=today)
    return resultat


def mettre_a_jour_materiel(db: Session, today: date, materiel: Optional[str] = None, **_) -> dict[str, Any]:
    """Change durablement le matériel du profil (déménagement, changement de salle).

    À ne pas confondre avec ``adapter_seance(motif="materiel")``, qui ne concerne que la
    séance d'aujourd'hui : ici c'est le profil qui change, donc toutes les séances à venir.
    """
    if not materiel:
        return {
            "ok": False,
            "clarification_requise": "Quel matériel est disponible désormais ?",
            "materiels_connus": sorted(substitution.MATERIEL_ONBOARDING_VERS_TAGS),
        }
    return _patch_profil(db, today, schemas.ProfilPatch(materiel=materiel))


# ---------------------------------------------------------------------------
# Registre : nom d'action -> implémentation
# ---------------------------------------------------------------------------

ACTIONS: dict[str, Callable[..., dict[str, Any]]] = {
    "get_profil": get_profil,
    "get_programme": get_programme,
    "generer_programme": generer_programme,
    "get_contexte_jour": get_contexte_jour,
    "get_seance_du_jour": get_seance_du_jour,
    "get_historique": get_historique,
    "get_progression_exercice": get_progression_exercice,
    "get_bilan": get_bilan,
    "get_contexte_signale": get_contexte_signale,
    "chercher_exercice": chercher_exercice,
    "enregistrer_performance": enregistrer_performance,
    "terminer_seance": terminer_seance,
    "adapter_seance": adapter_seance,
    "proposer_alternatives": proposer_alternatives,
    "remplacer_exercice": remplacer_exercice,
    "signaler_douleur": signaler_douleur,
    "signaler_fatigue": signaler_fatigue,
    "deplacer_match": deplacer_match,
    "mettre_a_jour_disponibilites": mettre_a_jour_disponibilites,
    "mettre_a_jour_materiel": mettre_a_jour_materiel,
}


def executer(nom: str, arguments: dict[str, Any], db: Session, today: date) -> dict[str, Any]:
    """Exécute une action du registre. Point d'entrée unique du coach et de l'API.

    Une action inconnue, des arguments invalides ou un refus métier ne remontent jamais en
    exception non gérée : ils deviennent un résultat ``{"ok": False, ...}`` que le coach sait
    formuler. Une exception inattendue est loguée puis traduite de la même façon, pour qu'un
    bug d'une action ne fasse pas tomber toute la conversation.
    """
    action = ACTIONS.get(nom)
    if action is None:
        return {"ok": False, "erreur": f"Action inconnue : {nom!r}."}

    if not isinstance(arguments, dict):
        return {"ok": False, "erreur": "Les arguments d'une action doivent être un objet JSON."}

    try:
        return action(db, today, **arguments)
    except ActionError as exc:
        return {"ok": False, "erreur": str(exc)}
    except TypeError as exc:
        logger.warning("Arguments invalides pour l'action %s : %s", nom, exc)
        return {"ok": False, "erreur": f"Arguments invalides pour {nom} : {exc}"}
    except Exception as exc:  # noqa: BLE001 -- une action qui casse ne doit pas tuer la conversation
        logger.exception("Échec de l'action coach %s", nom)
        db.rollback()
        return {"ok": False, "erreur": f"L'action {nom} a échoué : {exc}"}
