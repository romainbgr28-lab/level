import type { WeeklyReview, NewsItem } from '../types';

/**
 * Le bilan hebdomadaire et l'actu ne correspondent à aucune table du backend :
 * ils restent mockés pour l'instant.
 */

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
