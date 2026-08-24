# LEVEL

PWA de coaching personnel (force physique + développement intellectuel), installable sur iPhone via "Ajouter à l'écran d'accueil".

## Stack

React + Vite + TypeScript, `react-router-dom` pour la navigation, `vite-plugin-pwa` pour le manifest et le service worker. Backend FastAPI + SQLite (`backend/`) pour le profil, les séances, l'historique d'exercices, l'historique de séances (prévu/réalisé + contexte + phase calendaire), les modules d'apprentissage et les streaks. Le bilan hebdomadaire et l'actu n'ont pas de table dédiée et restent mockés (`src/data/mockData.ts`).

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
  api/          client.ts — appels fetch vers le backend
  types/        types partagés (contrat de données)
  data/         mockData.ts — bilan hebdomadaire + actu (pas de table backend)
  components/   Header, BottomNav, LineChart (SVG, pas de lib externe)
  screens/      un fichier par écran (Today, Workout, Module, Progress, WeeklyReview, News, Profile)
  App.tsx       routes
```
