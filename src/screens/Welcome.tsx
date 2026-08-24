interface WelcomeProps {
  onStart: () => void;
  error?: boolean;
}

export default function Welcome({ onStart, error }: WelcomeProps) {
  return (
    <div className="screen welcome-screen">
      <div className="welcome-screen__body">
        <h1 className="page-title" style={{ fontSize: 30, marginBottom: 10 }}>
          LEVEL
        </h1>
        <p className="subtle" style={{ fontSize: 15, marginBottom: 28 }}>
          Coaching personnel — force physique et développement intellectuel.
        </p>

        {error && (
          <p className="feedback feedback--ko" style={{ marginBottom: 20 }}>
            Impossible de contacter le serveur pour vérifier ton profil. Vérifie que le
            backend tourne (voir README), puis réessaie.
          </p>
        )}

        <button className="btn btn--primary" onClick={onStart}>
          Créer mon profil
        </button>
      </div>
    </div>
  );
}
