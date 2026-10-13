import { apiRequest } from './client'
import type {
  RecourseGenerateResponse,
  VerifyResponse,
  EditStatusUpdateResponse,
} from '../types/recourse'

export async function generateRecourse(
  resumeVersionId: string,
  jobDescriptionId: string,
): Promise<RecourseGenerateResponse> {
  return apiRequest<RecourseGenerateResponse>('/api/recourse/generate', {
    method: 'POST',
    body: JSON.stringify({
      resume_version_id: resumeVersionId,
      job_description_id: jobDescriptionId,
    }),
  })
}

export async function verifyRecourse(resumeVersionId: string): Promise<VerifyResponse> {
  return apiRequest<VerifyResponse>(`/api/recourse/${resumeVersionId}/verify`, {
    method: 'POST',
  })
}

export async function updateEditStatus(
  editId: string,
  action: 'confirm' | 'reject',
): Promise<EditStatusUpdateResponse> {
  return apiRequest<EditStatusUpdateResponse>(`/api/recourse/edits/${editId}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ action }),
  })
}
