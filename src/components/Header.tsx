import { useEffect, useState } from 'react';
import { getStats } from '../api/client';
import type { ApiStats } from '../api/client';

interface HeaderProps {
  title: string;
}

export default function Header({ title }: HeaderProps) {
  const [stats, setStats] = useState<ApiStats | null>(null);

  useEffect(() => {
    getStats().then(setStats).catch(() => setStats(null));
  }, []);

  return (
    <header className="app-header">
      <span className="app-header__title">{title}</span>
      <div className="app-header__stats">
        <span className="stat-pill stat-pill--flame" aria-label="Streak actuel">
          🔥 {stats?.streak ?? 0}
        </span>
        <span className="stat-pill stat-pill--xp" aria-label="XP total">
          ✦ {(stats?.xp_total ?? 0).toLocaleString('fr-FR')}
        </span>
      </div>
    </header>
  );
}
