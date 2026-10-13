export interface GroundingMetrics {
  evidence_grounding_rate: number
  unsupported_claim_rate: number
  original_fact_preservation_rate: number
}

export interface ExperimentRunCreate {
  resume_id: string
  job_description_id: string
  model_configuration: Record<string, unknown>
  baseline_method: string
  original_score: number
  final_score: number
  threshold: number
  decision_flipped: boolean
  total_edit_cost: number
  grounding_metrics: GroundingMetrics
  random_seed?: number | null
  edit_ids?: string[]
}

export interface ExperimentRunResponse {
  id: string
  resume_id: string
  job_description_id: string
  model_configuration: Record<string, unknown>
  baseline_method: string
  original_score: number
  final_score: number
  threshold: number
  decision_flipped: boolean
  total_edit_cost: number
  grounding_metrics: Record<string, number>
  random_seed: number | null
  created_at: string
}
