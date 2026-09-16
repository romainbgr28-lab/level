import { useCallback, useEffect, useState } from 'react';
import { getStats } from '../api/client';
import type { ApiStats } from '../api/client';
import { surDonneesModifiees } from '../utils/donneesFraiches';

interface HeaderProps {
  title: string;
}

export default function Header({ title }: HeaderProps) {
  const [stats, setStats] = useState<ApiStats | null>(null);

  const charger = useCallback(() => {
    getStats()
      .then(setStats)
      .catch(() => {
        /* En-tête décoratif : une panne réseau ne doit pas bloquer l'écran. On garde la
           dernière valeur connue plutôt que de la remettre à zéro, ce qui afficherait une
           régression de streak qui n'a pas eu lieu. */
      });
  }, []);

  useEffect(() => {
    charger();
    // L'en-tête reste monté d'un écran à l'autre : sans ça, le streak et l'XP resteraient
    // figés sur leur valeur d'ouverture après une séance terminée.
    return surDonneesModifiees((sujet) => {
      if (sujet === 'stats' || sujet === 'seance') charger();
    });
  }, [charger]);

  return (
    <header className="app-header">
      <span className="app-header__title">{title}</span>
      <div className="app-header__stats">
        {stats && (
          <>
            <span className="stat-pill stat-pill--flame" aria-label="Streak actuel">
              🔥 {stats.streak}
            </span>
            <span className="stat-pill stat-pill--xp" aria-label="XP total">
              ✦ {stats.xp_total.toLocaleString('fr-FR')}
            </span>
          </>
        )}
      </div>
    </header>
  );
}
