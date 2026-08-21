export interface UserStats {
  streak: number;
  recordStreak: number;
  xpTotal: number;
  totalSeances: number;
  totalModules: number;
  rpeAverage: number;
}

export interface ExerciseSet {
  reps: number;
  loadKg: number;
}

export interface Exercise {
  id: string;
  name: string;
  sets: ExerciseSet[];
}

export interface WorkoutOfDay {
  id: string;
  name: string;
  durationMin: number;
  exercises: Exercise[];
}

export type ModuleCategory =
  | 'Économie comportementale'
  | 'Psychologie cognitive'
  | 'Philosophie stoïcienne'
  | 'Finance personnelle';

export interface QcmQuestion {
  type: 'qcm';
  id: string;
  prompt: string;
  options: string[];
  correctIndex: number;
  explanation: string;
}

export interface OpenQuestion {
  type: 'open';
  id: string;
  prompt: string;
}

export type ModuleQuestion = QcmQuestion | OpenQuestion;

export interface LearningModule {
  id: string;
  title: string;
  category: ModuleCategory;
  hook: string;
  content: string;
  questions: ModuleQuestion[];
}

export interface CoachMessage {
  date: string;
  message: string;
}

export interface ChargeDataPoint {
  date: string;
  loadKg: number;
}

export interface ThemeScore {
  theme: ModuleCategory;
  percent: number;
}

export interface WeeklyReview {
  weekLabel: string;
  strength: { statement: string; evidence: string };
  weakness: { statement: string; evidence: string };
  adjustment: { statement: string; evidence: string };
}

export interface NewsItem {
  id: string;
  tag: string;
  title: string;
  summary: string;
  content: string;
}

export interface UserProfile {
  goals: string[];
  levelPhysical: string;
  levelIntellectual: string;
  timeConstraints: string;
  equipment: string;
}
