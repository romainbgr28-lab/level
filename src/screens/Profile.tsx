import Header from '../components/Header';
import { userProfile, userStats } from '../data/mockData';

export default function Profile() {
  return (
    <div className="screen">
      <Header title="Profil" />
      <h1 className="page-title">Profil</h1>

      <div className="section-title">Objectifs</div>
      <div className="tag-row">
        {userProfile.goals.map((g) => (
          <span className="tag" key={g}>
            {g}
          </span>
        ))}
      </div>

      <div className="section-title">Niveaux actuels</div>
      <div className="info-row">
        <span className="info-row__label">Physique</span>
        <span className="info-row__value">{userProfile.levelPhysical}</span>
      </div>
      <div className="info-row">
        <span className="info-row__label">Intellectuel</span>
        <span className="info-row__value">{userProfile.levelIntellectual}</span>
      </div>

      <div className="section-title">Contraintes & matériel</div>
      <div className="info-row">
        <span className="info-row__label">Temps disponible</span>
        <span className="info-row__value">{userProfile.timeConstraints}</span>
      </div>
      <div className="info-row">
        <span className="info-row__label">Matériel</span>
        <span className="info-row__value">{userProfile.equipment}</span>
      </div>

      <button className="btn btn--ghost" style={{ margin: '20px 0' }}>
        Modifier mes objectifs
      </button>

      <div className="stat-grid">
        <div className="stat-tile">
          <div className="stat-tile__value">{userStats.totalSeances}</div>
          <div className="stat-tile__label">Séances</div>
        </div>
        <div className="stat-tile">
          <div className="stat-tile__value">{userStats.totalModules}</div>
          <div className="stat-tile__label">Modules</div>
        </div>
        <div className="stat-tile">
          <div className="stat-tile__value">{userStats.recordStreak}</div>
          <div className="stat-tile__label">Record streak</div>
        </div>
      </div>
    </div>
  );
}
