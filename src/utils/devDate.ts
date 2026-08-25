// Simulation de la date courante, réservée au développement (build DEV Vite uniquement —
// désactivée automatiquement dans un build de production, cf. import.meta.env.DEV).
//
// Ne modifie ni les données réelles ni la date système : fournit seulement une "date
// courante" alternative aux endroits qui en ont besoin (semaine/jour du programme, écran
// Aujourd'hui) et, via le header X-Dev-Date, au backend (voir backend/dev_date.py — lui-même
// gardé par sa propre variable d'environnement DEV_MODE, ignorée en production).

const STORAGE_KEY = 'level_dev_simulated_date';

export const DEV_MODE_ENABLED = import.meta.env.DEV;

// Format YYYY-MM-DD, ou null si aucune simulation n'est active.
export function getDevSimulatedDate(): string | null {
  if (!DEV_MODE_ENABLED) return null;
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setDevSimulatedDate(dateStr: string | null): void {
  if (!DEV_MODE_ENABLED) return;
  try {
    if (dateStr) {
      localStorage.setItem(STORAGE_KEY, dateStr);
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    // localStorage indisponible (navigation privée, quota...) : simulation ignorée.
  }
}

// Remplace new Date() partout où le code doit connaître "aujourd'hui" côté frontend.
export function getNow(): Date {
  const override = getDevSimulatedDate();
  if (override) {
    const [y, m, d] = override.split('-').map(Number);
    return new Date(y, m - 1, d);
  }
  return new Date();
}
