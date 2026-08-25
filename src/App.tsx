import { useEffect, useState } from 'react';
import { Routes, Route } from 'react-router-dom';
import BottomNav from './components/BottomNav';
import Today from './screens/Today';
import Module from './screens/Module';
import Progress from './screens/Progress';
import Historique from './screens/Historique';
import Programme from './screens/Programme';
import WeeklyReview from './screens/WeeklyReview';
import News from './screens/News';
import Profile from './screens/Profile';
import Onboarding from './screens/Onboarding';
import Welcome from './screens/Welcome';
import { getProfil } from './api/client';

type AppStatus = 'checking' | 'welcome' | 'onboarding' | 'ready';

export default function App() {
  const [status, setStatus] = useState<AppStatus>('checking');
  const [profilFetchError, setProfilFetchError] = useState(false);

  useEffect(() => {
    getProfil()
      .then((profil) => setStatus(profil === null ? 'welcome' : 'ready'))
      .catch(() => {
        setProfilFetchError(true);
        setStatus('welcome');
      });
  }, []);

  if (status === 'checking') {
    return <div className="app-shell" />;
  }

  if (status === 'welcome') {
    return (
      <div className="app-shell">
        <Welcome error={profilFetchError} onStart={() => setStatus('onboarding')} />
      </div>
    );
  }

  if (status === 'onboarding') {
    return (
      <div className="app-shell">
        <Onboarding onDone={() => setStatus('ready')} />
      </div>
    );
  }

  return (
    <div className="app-shell">
      <Routes>
        <Route path="/" element={<Today />} />
        <Route path="/module" element={<Module />} />
        <Route path="/progression" element={<Progress />} />
        <Route path="/historique" element={<Historique />} />
        <Route path="/programme" element={<Programme />} />
        <Route path="/bilan" element={<WeeklyReview />} />
        <Route path="/actu" element={<News />} />
        <Route path="/profil" element={<Profile />} />
      </Routes>
      <BottomNav />
    </div>
  );
}
