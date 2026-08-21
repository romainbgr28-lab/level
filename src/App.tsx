import { useEffect, useState } from 'react';
import { Routes, Route } from 'react-router-dom';
import BottomNav from './components/BottomNav';
import Today from './screens/Today';
import Workout from './screens/Workout';
import Module from './screens/Module';
import Progress from './screens/Progress';
import WeeklyReview from './screens/WeeklyReview';
import News from './screens/News';
import Profile from './screens/Profile';
import Onboarding from './screens/Onboarding';
import { getProfil } from './api/client';

export default function App() {
  const [checkingProfil, setCheckingProfil] = useState(true);
  const [needsOnboarding, setNeedsOnboarding] = useState(false);

  useEffect(() => {
    getProfil()
      .then((profil) => setNeedsOnboarding(profil === null))
      .catch(() => setNeedsOnboarding(false))
      .finally(() => setCheckingProfil(false));
  }, []);

  if (checkingProfil) {
    return <div className="app-shell" />;
  }

  if (needsOnboarding) {
    return (
      <div className="app-shell">
        <Onboarding onDone={() => setNeedsOnboarding(false)} />
      </div>
    );
  }

  return (
    <div className="app-shell">
      <Routes>
        <Route path="/" element={<Today />} />
        <Route path="/seance" element={<Workout />} />
        <Route path="/module" element={<Module />} />
        <Route path="/progression" element={<Progress />} />
        <Route path="/bilan" element={<WeeklyReview />} />
        <Route path="/actu" element={<News />} />
        <Route path="/profil" element={<Profile />} />
      </Routes>
      <BottomNav />
    </div>
  );
}
