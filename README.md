# LEVEL

PWA de coaching personnel (force physique + développement intellectuel), installable sur iPhone via "Ajouter à l'écran d'accueil".

## V0 — Coach conversationnel

L'écran d'entrée de la V0 est une conversation (`src/screens/Coach.tsx`, route `/`). C'est une
interface **provisoire**, destinée à valider le cerveau de LEVEL avant de construire l'interface
finale : les écrans existants (Aujourd'hui, désormais sur `/aujourdhui`, Programme, Progression,
Profil, Historique, Bilan) sont conservés et restent accessibles par la navigation du bas.

Règle structurante : **le LLM n'est pas le moteur de décision.**

```
message → interprétation (LLM) → choix d'une action → MOTEUR (décision + écriture) → réponse (LLM)
```

Le modèle n'a aucun moyen d'écrire en base ni de calculer une charge, un volume ou un planning.
Sa seule surface d'action est le catalogue d'outils de `backend/coach.py`, miroir exact du
registre d'actions `backend/coach_actions.ACTIONS`. Un programme, une progression ou une semaine
« improvisés » par le modèle n'ont donc aucun chemin vers la base.

| Fichier | Rôle |
| --- | --- |
| `backend/coach.py` | Boucle d'orchestration (LLM ↔ outils), prompt système, catalogue d'outils. `repondre()` prend un `appel_llm` injectable : la boucle entière est testable sans clé API. |
| `backend/coach_actions.py` | Couche d'actions métier (20 actions). Frontière unique entre le langage et le moteur ; délègue à `main.py`, `regles_seance`, `moteur_decision`, `substitution`, `adaptation_seance`. |
| `backend/coach_contexte.py` | Contexte compact injecté au prompt (profil, objectifs, programme, jour, séance, historique borné, contraintes). Pur, sans I/O. |
| `backend/adaptation_seance.py` | Moteur d'adaptation d'une séance existante : durée, fatigue, matériel. Pur, sans I/O, sans IA. |

Trois invariants sont tenus par du code, pas par le prompt (un prompt se contourne, pas un `if`) :

1. **Aucune invention.** `enregistrer_performance` exige `series` et `repetitions` : « développé
   incliné lourd » ne peut structurellement pas produire un enregistrement, l'action renvoie la
   question à poser. Un nom d'exercice ambigu renvoie les candidats (`chercher_exercice`) plutôt
   qu'un choix arbitraire ; une progression sans données renvoie `assez_de_donnees: false`.
2. **Rien d'important ne reste dans la conversation.** Performances → `SerieLoggee` puis
   `HistoriqueSeance` ; douleur/fatigue → `ContexteSignale` ; match déplacé → `calendrier_matchs`,
   ce qui déclenche le recalcul du programme. Purger `messages_conversation` ne fait rien perdre
   au moteur (vérifié par `test_coach_actions.TestMemoireStructuree`).
3. **L'historique n'est jamais réécrit.** Aucune action ne modifie une séance terminée.

Endpoints : `POST /api/coach/message` (boucle complète), `POST /api/coach/action` (invocation
directe d'une action métier, sans LLM — raccourcis d'interface et tests), `GET /api/coach/conversation`,
`GET /api/coach/contexte` (lecture seule, ne génère rien).

Le coach utilise l'API Mistral en mode *function calling* (`mistral_client.appeler_mistral_outils`)
et nécessite donc `MISTRAL_API_KEY`. Sans elle, `POST /api/coach/message` répond 502 avec un message
clair — jamais une réponse de coach fabriquée : l'utilisateur doit pouvoir distinguer « LEVEL a
décidé ça » de « LEVEL n'a pas pu répondre ». Les actions métier (`POST /api/coach/action`), elles,
fonctionnent sans clé.

### Déplacement de match

`calendrier_matchs.annulations` (liste de dates) permet de retirer une occurrence du match habituel.
Sans elle, « mon match est finalement vendredi au lieu de samedi » ne pouvait qu'ajouter le vendredi :
le samedi restait un jour de match et l'utilisateur se retrouvait avec deux matchs dans la semaine.
Les deux lectures du calendrier (`calendrier.compute_phase`, `regles_seance._dates_matchs_proches`)
l'appliquent. Champ vide par défaut : un profil existant se comporte exactement comme avant.

## Stack

React + Vite + TypeScript, `react-router-dom` pour la navigation, `vite-plugin-pwa` pour le manifest et le service worker. Backend FastAPI + SQLite (`backend/`) pour le profil, les séances, l'historique d'exercices, l'historique de séances (prévu/réalisé + contexte + phase calendaire), les modules d'apprentissage et les streaks. Le bilan hebdomadaire est calculé à la volée depuis les séances réellement terminées et les séries loguées (`backend/bilan.py`, `GET /api/bilan/hebdomadaire`) : aucune donnée n'est mockée.

⚠️ SQLite ne migre pas automatiquement un changement de schéma : après avoir tiré une modification des modèles (`backend/models.py`), supprime `backend/level.db` avant de relancer `uvicorn`, sinon les anciennes colonnes/tables restent en place et l'API renverra des erreurs de validation.

## Génération de séance assistée (moteur de règles + Mistral)

`POST /api/seance/generer` et `POST /api/seance/terminer` combinent un moteur de règles pur Python (`backend/regles_seance.py`, aucun appel IA) et l'API Mistral (`mistral-small-latest`, via `backend/mistral_client.py`) :
- le moteur de règles calcule une recommandation structurée (phase calendaire, intensité max, priorités liées au poste, ajustement de charge/volume, exclusions) à partir du profil et de l'historique ;
- cette recommandation est envoyée à Mistral comme contexte contraignant pour générer les exercices concrets et leur explication ;
- `/api/seance/terminer` fait l'inverse : Mistral extrait un JSON structuré (exercices réalisés, RPE, % complété, zone sensible signalée) à partir d'un compte-rendu libre, puis l'XP est calculé en Python simple (pas par Mistral).

Nécessite la variable d'environnement `MISTRAL_API_KEY` (voir `backend/.env.example`) — à définir aussi dans les variables d'environnement Railway. Sans elle, ou si Mistral échoue/renvoie un JSON invalide, ces deux endpoints répondent une erreur HTTP 502 avec un message clair (jamais un plantage silencieux) ; l'erreur complète est aussi loguée côté serveur.

## Démarrer

Backend (API sur `http://localhost:8000`) :

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Frontend :

```bash
npm install
npm run dev
```

Le frontend appelle l'API sur `http://localhost:8000` par défaut ; surcharger avec la variable d'environnement Vite `VITE_API_BASE` si besoin.

## Build

```bash
npm run build
npm run preview
```

## Installer sur iPhone

1. Ouvrir l'app buildée (servie en HTTPS) dans Safari.
2. Partager → "Sur l'écran d'accueil".

## Structure

```
backend/
  main.py       endpoints REST FastAPI
  coach.py      boucle d'orchestration du coach conversationnel (LLM <-> actions métier)
  coach_actions.py couche d'actions métier exposée au coach (registre ACTIONS)
  coach_contexte.py contexte compact injecté au prompt (pur, sans I/O)
  adaptation_seance.py adaptation d'une séance existante : durée / fatigue / matériel (pur)
  models.py     tables SQLAlchemy (profil, seances, exercices_historique, modules_intellectuels,
                 sessions_apprentissage, streaks, historique_seances, messages_conversation,
                 contextes_signales)
  schemas.py    schémas Pydantic
  calendrier.py calcul de la phase calendaire de stockage (jour_de_match / veille / lendemain /
                 developpement) à partir du calendrier_matchs du profil — utilisé pour classer
                 historique_seances, distinct de regles_seance.calculer_phase_calendaire
  regles_seance.py moteur de règles pur Python (aucun appel IA) pour la génération de séance :
                 phase calendaire, priorités poste, ajustement de charge, garde-fous
  mistral_client.py client HTTP pour l'API Mistral (mode JSON), utilisé par les endpoints
                 /api/seance/generer et /api/seance/terminer
  seed.py       données initiales (module, séance du jour — le profil reste vide pour déclencher l'onboarding)
src/
  api/          client.ts — appels fetch vers le backend, ApiError (message lisible par
                 l'utilisateur pour toute erreur réseau/HTTP)
  types/        types partagés (contrat de données)
  data/         programmeTypes.ts — libellés et couleurs des types de séance
  components/   Header, BottomNav, LineChart (SVG, pas de lib externe), EtatEcran
                 (chargement / erreur / vide), Toast (retour discret après action)
  utils/        donneesFraiches.ts — invalidation des données après une mutation
  screens/      un fichier par écran (Coach, Today, Module, Programme, Progress, WeeklyReview,
                 Historique, Profile)
  App.tsx       routes
```

## Robustesse du parcours (états, reprise, idempotence)

Règle appliquée dans toute l'app : chaque écran dit ce qui se passe, pourquoi, et propose au
moins une action pour continuer — jamais un vide muet, jamais une erreur technique brute.

- **Erreurs** : `ApiError` (src/api/client.ts) transforme toute panne réseau ou réponse HTTP en
  une phrase lisible ; les refus métier du backend (jour de match, jour de repos, profil
  manquant) remontent tels quels dans `detail` et sont affichés avec l'alternative adaptée.
- **Reprise de séance** : le début de séance est persisté (`localStorage`), et une séance déjà
  commencée retrouvée au chargement propose « Reprendre / Terminer maintenant / Plus tard »
  plutôt que de replonger l'utilisateur dedans ou de repartir de zéro.
- **Idempotence** : `POST /api/seance/terminer` renvoie l'historique existant si la séance a
  déjà été terminée (jamais deux journaux, jamais deux fois l'XP) ;
  `POST /api/programme/generer` renvoie le programme actif sauf `regenerer: true` ;
  `POST /api/seance/generer` renvoie déjà la séance du jour existante. Côté frontend, chaque
  action critique est protégée par une garde synchrone anti double-clic.
- **Modification de profil** : `PATCH /api/profil` reconstruit le programme et renvoie
  `ProfilPatchOut` (`programme_recalcule`, `programme_erreur`, `seance_du_jour_supprimee`) —
  l'écran n'annonce un recalcul que s'il a eu lieu. L'historique n'est jamais touché ; seule
  une séance du jour **non commencée** devenue incohérente avec le nouveau planning est
  retirée.

