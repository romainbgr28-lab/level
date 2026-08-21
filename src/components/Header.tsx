import { userStats } from '../data/mockData';

interface HeaderProps {
  title: string;
}

export default function Header({ title }: HeaderProps) {
  return (
    <header className="app-header">
      <span className="app-header__title">{title}</span>
      <div className="app-header__stats">
        <span className="stat-pill stat-pill--flame" aria-label="Streak actuel">
          🔥 {userStats.streak}
        </span>
        <span className="stat-pill stat-pill--xp" aria-label="XP total">
          ✦ {userStats.xpTotal.toLocaleString('fr-FR')}
        </span>
      </div>
    </header>
  );
}
