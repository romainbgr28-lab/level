import { NavLink } from 'react-router-dom';

const items = [
  { to: '/', label: 'Aujourd’hui', icon: TodayIcon },
  { to: '/progression', label: 'Progression', icon: ProgressIcon },
  { to: '/actu', label: 'Actu', icon: NewsIcon },
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

function TodayIcon() {
  return (
    <svg className="nav-item__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <rect x="3.5" y="4.5" width="17" height="16" rx="3" />
      <path d="M3.5 9.5h17M8 3v3M16 3v3" strokeLinecap="round" />
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

function NewsIcon() {
  return (
    <svg className="nav-item__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <rect x="3.5" y="4.5" width="17" height="15" rx="2" />
      <path d="M7.5 9h9M7.5 12.5h9M7.5 16h5" strokeLinecap="round" />
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
