import { apiRequest } from './client'
import type { ExperimentRunCreate, ExperimentRunResponse } from '../types/experiment'

export async function createExperiment(payload: ExperimentRunCreate): Promise<ExperimentRunResponse> {
  return apiRequest<ExperimentRunResponse>('/api/experiments', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function getExperiment(id: string): Promise<ExperimentRunResponse> {
  return apiRequest<ExperimentRunResponse>(`/api/experiments/${id}`)
}
