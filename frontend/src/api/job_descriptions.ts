import { apiRequest } from './client'
import type { JobDescriptionResponse } from '../types/resume'

export async function createJobDescription(text: string): Promise<JobDescriptionResponse> {
  return apiRequest<JobDescriptionResponse>('/api/job-descriptions', {
    method: 'POST',
    body: JSON.stringify({ text }),
  })
}
