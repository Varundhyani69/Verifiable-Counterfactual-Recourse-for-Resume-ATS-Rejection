import { apiRequest } from './client'
import type { AnalysisResponse } from '../types/analysis'

export async function runAnalysis(resumeId: string, jobDescriptionId: string): Promise<AnalysisResponse> {
  return apiRequest<AnalysisResponse>('/api/analysis', {
    method: 'POST',
    body: JSON.stringify({
      resume_id: resumeId,
      job_description_id: jobDescriptionId,
      scoring_config: {
        skill_overlap_weight: 0.5,
        sbert_weight: 0.5,
        threshold: 0.5,
      },
    }),
  })
}
