export interface CandidateFactResponse {
  id: string
  candidate_id: string
  claim_text: string
  original_claim_text: string
  claim_type: string
  source_document_id: string
  source_span: Record<string, number>
  verification_status: string
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface EvidenceResponse {
  candidate_id: string
  facts: CandidateFactResponse[]
}

export interface FactPatch {
  claim_text?: string
  verification_status?: string
}
