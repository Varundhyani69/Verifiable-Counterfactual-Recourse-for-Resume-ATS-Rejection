export interface ProposedEditResponse {
  id: string
  original_text: string
  proposed_text: string
  edit_type: string
  evidence_fact_ids: string[]
  job_requirement_ids: string[]
  verification_status: string
  edit_cost: number
  score_contribution: number
}

export interface PartialResult {
  edits: ExplanationCardResponse[]
  total_edit_cost: number
  projected_score: number
}

export interface RecourseGenerateResponse {
  recourse_id: string
  status: 'feasible' | 'infeasible'
  accepted_edits?: ExplanationCardResponse[]
  total_edit_cost?: number
  projected_score?: number
  projected_decision?: 'pass' | 'fail'
  reason?: string
  detail?: string
  constraints_violated?: string[]
  partial_result?: PartialResult
}

export interface ExplanationCardResponse {
  edit_id: string
  prose_description: string
  ats_improvement_reason: string
  evidence_fact_ids: string[]
  evidence_claim_texts: string[]
  job_requirement_ids: string[]
  requirement_texts: string[]
  score_contribution: number
  edit_cost: number
  verification_status: string
  edit_type: string
  original_text: string
  proposed_text: string
  can_confirm: boolean
  can_reject: boolean
}

export interface AggregateMetricsResponse {
  total_edit_cost: number
  projected_final_score: number | null
  projected_decision: string | null
  overall_grounding_rate: number
  unsupported_claim_rate: number
}

export interface VerificationReportResponse {
  edit_id: string
  methods_used: string[]
  evidence_fact_ids: string[]
  assigned_status: string
  entailment_score: number
  rationale: string
}

export interface VerifyResponse {
  resume_version_id: string
  verification_reports: VerificationReportResponse[]
}

export interface EditStatusUpdateResponse {
  edit_id: string
  verification_status: string
  action_applied: string
}
