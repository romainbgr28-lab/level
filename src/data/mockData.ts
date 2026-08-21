import type {
  UserStats,
  WorkoutOfDay,
  LearningModule,
  CoachMessage,
  ChargeDataPoint,
  ThemeScore,
  WeeklyReview,
  NewsItem,
  UserProfile,
} from '../types';

/**
 * Toutes les données sont mockées mais cohérentes entre les écrans :
 * - streak / xp / totaux identiques partout où ils apparaissent
 * - la charge du dernier point du graphique correspond à la charge du jour
 */

export const userStats: UserStats = {
  streak: 12,
  recordStreak: 21,
  xpTotal: 3480,
  totalSeances: 87,
  totalModules: 34,
  rpeAverage: 7.2,
};

export const todaysWorkout: WorkoutOfDay = {
  id: 'w-push-force',
  name: 'Push Day — Force',
  durationMin: 45,
  exercises: [
    {
      id: 'ex-1',
      name: 'Développé couché',
      sets: [
        { reps: 6, loadKg: 80 },
        { reps: 6, loadKg: 80 },
        { reps: 6, loadKg: 80 },
        { reps: 6, loadKg: 80 },
      ],
    },
    {
      id: 'ex-2',
      name: 'Développé militaire',
      sets: [
        { reps: 8, loadKg: 45 },
        { reps: 8, loadKg: 45 },
        { reps: 8, loadKg: 45 },
      ],
    },
    {
      id: 'ex-3',
      name: 'Dips lestés',
      sets: [
        { reps: 10, loadKg: 15 },
        { reps: 10, loadKg: 15 },
        { reps: 10, loadKg: 15 },
      ],
    },
    {
      id: 'ex-4',
      name: 'Élévations latérales',
      sets: [
        { reps: 12, loadKg: 10 },
        { reps: 12, loadKg: 10 },
        { reps: 12, loadKg: 10 },
      ],
    },
    {
      id: 'ex-5',
      name: 'Extensions triceps poulie',
      sets: [
        { reps: 12, loadKg: 20 },
        { reps: 12, loadKg: 20 },
        { reps: 12, loadKg: 20 },
      ],
    },
    {
      id: 'ex-6',
      name: 'Gainage',
      sets: [
        { reps: 1, loadKg: 0 },
        { reps: 1, loadKg: 0 },
        { reps: 1, loadKg: 0 },
      ],
    },
  ],
};

export const todaysModule: LearningModule = {
  id: 'm-biais-confirmation',
  title: 'Le biais de confirmation',
  category: 'Économie comportementale',
  hook: 'Pourquoi tu ignores systématiquement les preuves qui te contredisent.',
  content: `Le biais de confirmation est notre tendance naturelle à rechercher, interpréter et
mémoriser les informations qui confirment nos croyances existantes, tout en accordant
moins de poids aux informations qui les contredisent. Ce mécanisme n'est pas un défaut
de caractère : c'est un raccourci cognitif que le cerveau utilise pour économiser de
l'énergie et réduire la dissonance psychologique liée au fait de se tromper.

Dans la pratique, ce biais se manifeste de trois façons. D'abord, la recherche
sélective d'information : on consulte davantage les sources qui vont dans notre sens.
Ensuite, l'interprétation biaisée : face à une preuve ambiguë, on l'interprète en
faveur de ce qu'on pense déjà. Enfin, la mémoire sélective : on se souvient mieux des
faits qui confirment nos idées que de ceux qui les infirment.

Ce biais a un coût réel. En entraînement, il pousse à ne retenir que les séances
réussies et à minimiser les signaux de surmenage. En finance, il pousse à ne lire que
les analyses qui confirment une décision d'investissement déjà prise. En discussion,
il transforme un débat en course à la validation plutôt qu'en recherche de la vérité.

La parade la plus efficace n'est pas de « faire un effort de neutralité », ce qui ne
fonctionne presque jamais, mais de mettre en place des procédures : chercher
activement l'argument le plus solide qui s'oppose à sa position, demander à quelqu'un
de jouer l'avocat du diable, ou tenir un journal où l'on note ses prédictions avant de
connaître le résultat. Ces garde-fous externes compensent ce que la seule volonté ne
peut pas corriger.`,
  questions: [
    {
      type: 'open',
      id: 'q1',
      prompt:
        'Décris une situation récente où tu as probablement ignoré une information qui contredisait ton opinion.',
    },
    {
      type: 'qcm',
      id: 'q2',
      prompt: 'Le biais de confirmation nous pousse principalement à…',
      options: [
        'Changer d’avis dès qu’une preuve contraire apparaît',
        'Rechercher, interpréter et mémoriser ce qui confirme nos croyances existantes',
        'Éviter toute prise de décision',
        'Ne faire confiance qu’aux experts',
      ],
      correctIndex: 1,
      explanation:
        'Exact : c’est un raccourci cognitif qui économise de l’énergie mentale en évitant la dissonance liée au fait de se tromper.',
    },
    {
      type: 'qcm',
      id: 'q3',
      prompt: 'Quelle est la parade la plus fiable contre ce biais ?',
      options: [
        'Faire un effort de volonté pour rester neutre',
        'Éviter les sujets sensibles',
        'Mettre en place des procédures externes (avocat du diable, journal de prédictions)',
        'Lire uniquement des sources qui nous contredisent',
      ],
      correctIndex: 2,
      explanation:
        'La volonté seule est peu efficace contre ce biais : des garde-fous structurels et externes fonctionnent bien mieux.',
    },
  ],
};

export const coachMessage: CoachMessage = {
  date: new Date().toISOString(),
  message:
    'Bonne récupération hier, on monte légèrement la charge aujourd’hui sur le développé couché (+2,5 kg).',
};

// Évolution de la charge sur le Développé couché — dernières 8 séances
export const benchPressProgress: ChargeDataPoint[] = [
  { date: '10 juil.', loadKg: 70 },
  { date: '15 juil.', loadKg: 72 },
  { date: '20 juil.', loadKg: 72 },
  { date: '27 juil.', loadKg: 75 },
  { date: '3 août', loadKg: 75 },
  { date: '9 août', loadKg: 77.5 },
  { date: '15 août', loadKg: 80 },
  { date: '21 août', loadKg: 80 },
];

export const themeScores: ThemeScore[] = [
  { theme: 'Philosophie stoïcienne', percent: 82 },
  { theme: 'Économie comportementale', percent: 68 },
  { theme: 'Psychologie cognitive', percent: 54 },
  { theme: 'Finance personnelle', percent: 45 },
];

// Grille des 35 derniers jours — le streak actuel (12) correspond aux 12 dernières cases actives
export const streakHistory: boolean[] = (() => {
  const days = 35;
  const arr = new Array(days).fill(false);
  // 12 derniers jours actifs (streak en cours)
  for (let i = days - 12; i < days; i++) arr[i] = true;
  // activité éparse avant la pause qui a précédé le streak actuel
  const sparse = [0, 1, 2, 4, 5, 7, 8, 9, 11, 13, 14, 15, 17, 18, 20];
  sparse.forEach((i) => (arr[i] = true));
  return arr;
})();

export const weeklyReview: WeeklyReview = {
  weekLabel: 'Semaine du 11 au 17 août',
  strength: {
    statement: 'Régularité sportive excellente',
    evidence: '6 séances sur 7 réalisées cette semaine',
  },
  weakness: {
    statement: 'Score du module « Finance personnelle » en retrait',
    evidence: '45 % de bonnes réponses sur les 3 derniers quiz',
  },
  adjustment: {
    statement: 'On augmente légèrement les charges du haut du corps la semaine prochaine',
    evidence: 'RPE moyen de 6,8/10 sur les séances push : marge de progression disponible',
  },
};

export const newsItems: NewsItem[] = [
  {
    id: 'n1',
    tag: 'Nutrition',
    title: 'Le mythe de la fenêtre anabolique',
    summary: 'Ce que dit vraiment la recherche sur le timing des protéines après l’effort.',
    content:
      'Pendant longtemps, on a cru qu’il fallait consommer des protéines dans les 30 minutes suivant une séance sous peine de perdre le bénéfice de l’entraînement. Les méta-analyses récentes montrent que cette « fenêtre anabolique » est bien plus large que prévu : l’apport protéique total sur la journée compte davantage que le timing précis. Ce qui reste vrai : répartir ses protéines sur 3 à 4 prises quotidiennes optimise la synthèse protéique musculaire mieux qu’une seule grosse prise.',
  },
  {
    id: 'n2',
    tag: 'Mental',
    title: 'La discipline bat la motivation',
    summary: 'Pourquoi compter sur sa motivation est une stratégie perdante à long terme.',
    content:
      'La motivation est une ressource émotionnelle instable, dépendante du sommeil, du stress et de l’humeur. La discipline, elle, repose sur des systèmes : horaires fixes, environnement préparé à l’avance, engagements publics. Les personnes qui tiennent leurs objectifs sur plusieurs années ne sont pas plus motivées que les autres — elles ont simplement réduit le nombre de décisions à prendre au moment d’agir.',
  },
  {
    id: 'n3',
    tag: 'Recherche',
    title: 'Sommeil et récupération musculaire',
    summary: 'Moins de 7h de sommeil réduit mesurablement les gains de force.',
    content:
      'Plusieurs études convergent : dormir moins de 7 heures par nuit de façon répétée diminue la sécrétion d’hormone de croissance nocturne et augmente le cortisol, deux facteurs qui freinent directement la récupération musculaire. Un déficit de sommeil chronique peut réduire les gains de force de 20 à 30 % à volume d’entraînement identique. Prioriser le sommeil a souvent plus d’impact sur la progression qu’un ajustement du programme.',
  },
];

export const userProfile: UserProfile = {
  goals: ['Force', 'Discipline mentale', 'Régularité'],
  levelPhysical: 'Intermédiaire',
  levelIntellectual: 'Avancé',
  timeConstraints: '3 à 4 séances / semaine, 45 min max',
  equipment: 'Salle de sport complète + haltères à domicile',
};
