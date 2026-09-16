import { NavLink } from 'react-router-dom';

const items = [
  // V0 : le coach est l'écran d'entrée. Les écrans existants restent accessibles d'un geste —
  // rien n'est retiré, seul l'ordre change pour refléter ce qu'on cherche à valider.
  { to: '/', label: 'Coach', icon: CoachIcon },
  { to: '/aujourdhui', label: 'Aujourd’hui', icon: TodayIcon },
  // Le programme est la réponse à « où j'en suis » : il doit être atteignable en un geste,
  // pas seulement via un lien enfoui dans l'écran Progression.
  { to: '/programme', label: 'Programme', icon: ProgrammeIcon },
  { to: '/progression', label: 'Progression', icon: ProgressIcon },
  { to: '/profil', label: 'Profil', icon: ProfileIcon },
];

export default function BottomNav() {
  return (
    <nav className="bottom-nav">
      {items.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/'}
          className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
        >
          <Icon />
          <span>{label}</span>
        </NavLink>
      ))}
    </nav>
  );
}

function CoachIcon() {
  return (
    <svg className="nav-item__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M4.5 5.5h15v11h-9l-4 3.5v-3.5h-2z" strokeLinejoin="round" />
    </svg>
  );
}

function TodayIcon() {
  return (
    <svg className="nav-item__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <rect x="3.5" y="4.5" width="17" height="16" rx="3" />
      <path d="M3.5 9.5h17M8 3v3M16 3v3" strokeLinecap="round" />
    </svg>
  );
}

function ProgrammeIcon() {
  return (
    <svg className="nav-item__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M4 6h16M4 12h10M4 18h13" strokeLinecap="round" />
    </svg>
  );
}

function ProgressIcon() {
  return (
    <svg className="nav-item__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M4 20V13M10 20V8M16 20V11M22 20V4" strokeLinecap="round" />
    </svg>
  );
}

function ProfileIcon() {
  return (
    <svg className="nav-item__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <circle cx="12" cy="8" r="3.5" />
      <path d="M4.5 20c1.4-4 4.2-6 7.5-6s6.1 2 7.5 6" strokeLinecap="round" />
    </svg>
  );
}
