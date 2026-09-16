interface WelcomeProps {
  onStart: () => void;
}

export default function Welcome({ onStart }: WelcomeProps) {
  return (
    <div className="screen welcome-screen">
      <div className="welcome-screen__body">
        <h1 className="page-title" style={{ fontSize: 30, marginBottom: 10 }}>
          LEVEL
        </h1>
        <p className="subtle" style={{ fontSize: 15, marginBottom: 18 }}>
          Coaching personnel — force physique et développement intellectuel.
        </p>
        {/* L'utilisateur doit savoir à quoi il s'engage avant de commencer : combien d'étapes,
            pourquoi ces questions, et ce qu'il obtient au bout. */}
        <p className="subtle" style={{ marginBottom: 28 }}>
          Quelques questions sur tes objectifs, ton sport et tes disponibilités : LEVEL s’en sert
          pour construire ton programme et décider ce que tu fais chaque jour. Tu pourras tout
          modifier ensuite.
        </p>

        <button className="btn btn--primary" onClick={onStart}>
          Créer mon profil
        </button>
      </div>
    </div>
  );
}
