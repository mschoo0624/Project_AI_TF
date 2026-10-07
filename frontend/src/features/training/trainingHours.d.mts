export type TrainingSessionHours = { day_number: number; credited_hours: number }
export type TrainingHourPreset = { day_number: number; hours: number; label: string }
export type ResolvedTrainingHours = {
  hours: number
  automatic: boolean
  capped: boolean
  limitUnknown: boolean
}

export function buildTrainingHourPresets(sessions: TrainingSessionHours[]): TrainingHourPreset[]
export function resolveTrainingHours(input: {
  isTypeII: boolean
  result: string
  eventHours: number
  requiredHours: number | null
  remainingHours: number | null
  enteredHours: number
}): ResolvedTrainingHours
export function bulkHourExclusionReason(
  hours: number,
  eventHours: number,
  remainingHours: number | null,
): 'unknown_remaining' | 'event_capacity' | 'annual_allowance' | null
