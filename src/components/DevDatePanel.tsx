import { useState } from 'react';
import { DEV_MODE_ENABLED, getDevSimulatedDate, setDevSimulatedDate } from '../utils/devDate';

// Panneau visible uniquement en environnement de développement (import.meta.env.DEV) —
// n'apparaît jamais dans un build de production. Permet de simuler la date "aujourd'hui"
// pour tester le programme (semaine/jour, séance du jour, adaptation) sans attendre le
// temps réel. Ne modifie ni la date système, ni les données réelles en base.
export default function DevDatePanel() {
  const [input, setInput] = useState(getDevSimulatedDate() ?? '');
  const simulee = getDevSimulatedDate();

  if (!DEV_MODE_ENABLED) return null;

  function handleAppliquer() {
    if (!input) return;
    setDevSimulatedDate(input);
    window.location.reload();
  }

  function handleReinitialiser() {
    setDevSimulatedDate(null);
    window.location.reload();
  }

  return (
    <>
      <div className="section-title">Mode développeur</div>
      <div
        style={{
          border: '1px dashed var(--danger, #e5484d)',
          borderRadius: 8,
          padding: 12,
          marginBottom: 14,
        }}
      >
        <p className="subtle" style={{ margin: '0 0 10px' }}>
          Simule la date courante pour tester le programme (semaine, séance du jour,
          adaptation) sans attendre. N'affecte pas les données réelles.
        </p>
        <div className="info-row">
          <span className="info-row__label">Date réelle</span>
          <span className="info-row__value">{new Date().toLocaleDateString('fr-FR')}</span>
        </div>
        <div className="info-row">
          <span className="info-row__label">Date simulée</span>
          <span className="info-row__value">
            {simulee ? new Date(simulee).toLocaleDateString('fr-FR') : 'Aucune (date réelle)'}
          </span>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', margin: '10px 0' }}>
          <input
            type="date"
            className="textarea"
            style={{ minHeight: 'unset', padding: 8, flex: 1 }}
            value={input}
            onChange={(e) => setInput(e.target.value)}
          />
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn--primary btn--sm" disabled={!input} onClick={handleAppliquer}>
            Appliquer
          </button>
          <button className="btn btn--ghost btn--sm" disabled={!simulee} onClick={handleReinitialiser}>
            Réinitialiser
          </button>
        </div>
      </div>
    </>
  );
}
