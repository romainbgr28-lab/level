import { useCallback, useEffect, useState } from 'react';
import { Routes, Route } from 'react-router-dom';
import BottomNav from './components/BottomNav';
import ToastHost from './components/Toast';
import { EtatChargement, EtatErreur } from './components/EtatEcran';
import Coach from './screens/Coach';
import Today from './screens/Today';
import Module from './screens/Module';
import Progress from './screens/Progress';
import Historique from './screens/Historique';
import Programme from './screens/Programme';
import WeeklyReview from './screens/WeeklyReview';
import Profile from './screens/Profile';
import Onboarding from './screens/Onboarding';
import Welcome from './screens/Welcome';
import { getProfil, messageErreur } from './api/client';

type AppStatus = 'checking' | 'erreur' | 'welcome' | 'onboarding' | 'ready';

export default function App() {
  const [status, setStatus] = useState<AppStatus>('checking');
  const [erreur, setErreur] = useState<string | null>(null);

  const verifierProfil = useCallback(() => {
    setStatus('checking');
    setErreur(null);
    getProfil()
      .then((profil) => setStatus(profil === null ? 'welcome' : 'ready'))
      .catch((e) => {
        // On ne sait pas si un profil existe : proposer « Créer mon profil » ferait
        // recommencer l'onboarding à quelqu'un qui en a déjà un. On dit ce qui se passe et on
        // propose de réessayer, sans rien décider à sa place.
        setErreur(messageErreur(e, 'Impossible de contacter le serveur.'));
        setStatus('erreur');
      });
  }, []);

  useEffect(verifierProfil, [verifierProfil]);

  if (status === 'checking') {
    return (
      <div className="app-shell">
        <div className="screen">
          <EtatChargement message="Ouverture de LEVEL…" />
        </div>
      </div>
    );
  }

  if (status === 'erreur') {
    return (
      <div className="app-shell">
        <div className="screen">
          <h1 className="page-title" style={{ fontSize: 30 }}>
            LEVEL
          </h1>
          <EtatErreur
            titre="LEVEL n’arrive pas à démarrer"
            message={`${erreur ?? 'Erreur inconnue.'} Tes données ne sont pas perdues : elles sont enregistrées côté serveur.`}
            action={{ label: 'Réessayer', onClick: verifierProfil }}
            actionSecondaire={{
              label: 'Commencer sans attendre',
              onClick: () => setStatus('onboarding'),
            }}
          />
        </div>
      </div>
    );
  }

  if (status === 'welcome') {
    return (
      <div className="app-shell">
        <Welcome onStart={() => setStatus('onboarding')} />
        <ToastHost />
      </div>
    );
  }

  if (status === 'onboarding') {
    return (
      <div className="app-shell">
        <Onboarding onDone={() => setStatus('ready')} />
        <ToastHost />
      </div>
    );
  }

  return (
    <div className="app-shell">
      <Routes>
        {/* V0 : le coach conversationnel est l'écran d'entrée (spécification section 26,
            onboarding -> programme -> coach). Les écrans existants ne sont pas supprimés —
            ils restent accessibles, Aujourd'hui passant simplement de « / » à « /aujourdhui ». */}
        <Route path="/" element={<Coach />} />
        <Route path="/aujourdhui" element={<Today />} />
        <Route path="/module" element={<Module />} />
        <Route path="/progression" element={<Progress />} />
        <Route path="/historique" element={<Historique />} />
        <Route path="/programme" element={<Programme />} />
        <Route path="/bilan" element={<WeeklyReview />} />
        <Route path="/profil" element={<Profile />} />
      </Routes>
      <BottomNav />
      <ToastHost />
    </div>
  );
}
