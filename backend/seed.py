from datetime import date

from database import SessionLocal
from models import ModuleIntellectuel, Streak


def seed(db):
    # Le profil n'est volontairement pas pré-rempli : la table doit rester vide
    # tant que l'utilisateur n'a pas complété l'onboarding (voir GET /api/profil
    # et l'écran Onboarding côté frontend, affiché uniquement si profil est null).

    if db.query(ModuleIntellectuel).count() == 0:
        db.add(
            ModuleIntellectuel(
                categorie="Économie comportementale",
                niveau="Avancé",
                titre="Le biais de confirmation",
                contenu=(
                    "Le biais de confirmation est notre tendance naturelle à rechercher, interpréter et "
                    "mémoriser les informations qui confirment nos croyances existantes, tout en accordant "
                    "moins de poids aux informations qui les contredisent. Ce mécanisme n'est pas un défaut "
                    "de caractère : c'est un raccourci cognitif que le cerveau utilise pour économiser de "
                    "l'énergie et réduire la dissonance psychologique liée au fait de se tromper.\n\n"
                    "Dans la pratique, ce biais se manifeste de trois façons. D'abord, la recherche "
                    "sélective d'information : on consulte davantage les sources qui vont dans notre sens. "
                    "Ensuite, l'interprétation biaisée : face à une preuve ambiguë, on l'interprète en "
                    "faveur de ce qu'on pense déjà. Enfin, la mémoire sélective : on se souvient mieux des "
                    "faits qui confirment nos idées que de ceux qui les infirment.\n\n"
                    "Ce biais a un coût réel. En entraînement, il pousse à ne retenir que les séances "
                    "réussies et à minimiser les signaux de surmenage. En finance, il pousse à ne lire que "
                    "les analyses qui confirment une décision d'investissement déjà prise. En discussion, "
                    "il transforme un débat en course à la validation plutôt qu'en recherche de la vérité.\n\n"
                    "La parade la plus efficace n'est pas de « faire un effort de neutralité », ce qui ne "
                    "fonctionne presque jamais, mais de mettre en place des procédures : chercher "
                    "activement l'argument le plus solide qui s'oppose à sa position, demander à quelqu'un "
                    "de jouer l'avocat du diable, ou tenir un journal où l'on note ses prédictions avant de "
                    "connaître le résultat. Ces garde-fous externes compensent ce que la seule volonté ne "
                    "peut pas corriger."
                ),
                questions=[
                    {
                        "type": "open",
                        "id": "q1",
                        "prompt": "Décris une situation récente où tu as probablement ignoré une information qui contredisait ton opinion.",
                    },
                    {
                        "type": "qcm",
                        "id": "q2",
                        "prompt": "Le biais de confirmation nous pousse principalement à…",
                        "options": [
                            "Changer d’avis dès qu’une preuve contraire apparaît",
                            "Rechercher, interpréter et mémoriser ce qui confirme nos croyances existantes",
                            "Éviter toute prise de décision",
                            "Ne faire confiance qu’aux experts",
                        ],
                        "correctIndex": 1,
                        "explanation": "Exact : c’est un raccourci cognitif qui économise de l’énergie mentale en évitant la dissonance liée au fait de se tromper.",
                    },
                    {
                        "type": "qcm",
                        "id": "q3",
                        "prompt": "Quelle est la parade la plus fiable contre ce biais ?",
                        "options": [
                            "Faire un effort de volonté pour rester neutre",
                            "Éviter les sujets sensibles",
                            "Mettre en place des procédures externes (avocat du diable, journal de prédictions)",
                            "Lire uniquement des sources qui nous contredisent",
                        ],
                        "correctIndex": 2,
                        "explanation": "La volonté seule est peu efficace contre ce biais : des garde-fous structurels et externes fonctionnent bien mieux.",
                    },
                ],
            )
        )

    # Pas de séance seedée pour aujourd'hui : la séance du jour doit venir de
    # /api/seance/generer (moteur de règles + Mistral). Si on en pré-crée une ici,
    # GET /api/seances/today la trouve toujours en premier et l'écran Aujourd'hui
    # n'affiche jamais le bouton "Générer ma séance du jour" — le flux IA n'est
    # alors jamais réellement exercé.

    if db.query(Streak).count() == 0:
        db.add(Streak(date=date.today(), sport_fait=0, apprentissage_fait=0))

    db.commit()


if __name__ == "__main__":
    session = SessionLocal()
    try:
        seed(session)
    finally:
        session.close()
