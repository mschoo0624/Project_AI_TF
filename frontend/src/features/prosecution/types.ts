export type Target = { military_number: string; name: string }

export type Training = {
  id: number
  training_type: string
  training_round: number
  service_year: number
  dates: string[]
  attendance_status: string
  confirmed_by: string
  // Older saved documents do not include the extended training facts.
  schedule_title?: string
  training_year?: number | null
  scheduled_hours?: number | null
  completed_hours?: number
  confirmed_at?: string | null
}

export type DraftSources = {
  person: Target & { rank: string; reserve_unit: string }
  is_target: boolean
  reasons: string[]
  records: Training[]
}

export type DraftFields = Record<string, string>

export type SavedDocumentSummary = {
  id: string
  person_id: string
  name: string
  document_number: string
  version: number
  created_at: string
  updated_at: string
}

export type SavedDocument = {
  id: string
  person_id: string
  fields: DraftFields
  training_record_ids: number[]
  training_snapshot: Training[]
  version: number
  created_at: string
  updated_at: string
}

export type ProsecutionTarget = Target & {
  branch: string
  rank: string | null
  service_year: number | null
  squad_id: number | null
  prosecution_reason: string | null
  consecutive_unexcused_absences: number
  target_years: number[]
}

export type TrainingReviewTarget = Target & {
  branch: string
  rank: string | null
  service_year: number
  squad_id: number | null
  review_years: number[]
  remaining_hours: number
}

export type ProsecutionTrainingProgress = {
  service_year: number
  training_plan: { name: string; hours: number }[]
  required_hours: number
  completed_hours: number
  remaining_hours: number
  training_status: string
  prosecution_risk: boolean
}

export type ProsecutionTrainingRecord = {
  id: number
  education_year: number
  training_year: number | null
  training_type: string
  training_round: number
  attendance_status: string
  training_hours: number
}
