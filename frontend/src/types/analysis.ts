export interface ScoreBreakdown {
  total_score: number
  skill_overlap_score: number
  semantic_similarity_score: number
  weights: Record<string, number>
  threshold: number
}

export interface AnalysisResponse {
  resume_version_id: string
  version_number: number
  score_breakdown: ScoreBreakdown
  decision: 'pass' | 'fail'
  disclosure: string
}

export interface ScoringConfigRequest {
  skill_overlap_weight: number
  sbert_weight: number
  threshold: number
}
