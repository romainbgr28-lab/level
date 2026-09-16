# LEVEL

PWA de coaching personnel (force physique + développement intellectuel), installable sur iPhone via "Ajouter à l'écran d'accueil".

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
  models.py     tables SQLAlchemy (profil, seances, exercices_historique, modules_intellectuels,
                 sessions_apprentissage, streaks, historique_seances)
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
  screens/      un fichier par écran (Today, Module, Programme, Progress, WeeklyReview, Historique, Profile)
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

