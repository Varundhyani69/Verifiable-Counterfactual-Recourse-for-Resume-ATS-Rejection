import { apiRequest } from './client'
import type { CandidateFactResponse, EvidenceResponse, FactPatch } from '../types/candidate'

export async function getEvidence(candidateId: string): Promise<EvidenceResponse> {
  return apiRequest<EvidenceResponse>(`/api/candidates/${candidateId}/evidence`)
}

export async function patchFact(
  candidateId: string,
  factId: string,
  patch: FactPatch,
): Promise<CandidateFactResponse> {
  return apiRequest<CandidateFactResponse>(
    `/api/candidates/${candidateId}/evidence/${factId}`,
    {
      method: 'PATCH',
      body: JSON.stringify(patch),
    },
  )
}
