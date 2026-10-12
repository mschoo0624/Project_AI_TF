export const trainingTabs = [
  { id: 'schedule', label: '훈련일정' },
  { id: 'assignment', label: '훈련부과' },
  { id: 'results', label: '훈련결과' },
] as const

export type TrainingTabId = typeof trainingTabs[number]['id']