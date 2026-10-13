import { apiRequest } from './client'
import type { ResumeDocumentResponse } from '../types/resume'

export async function uploadResumeFile(file: File, candidateId: string): Promise<ResumeDocumentResponse> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('candidate_id', candidateId)
  return apiRequest<ResumeDocumentResponse>('/api/resumes/upload', {
    method: 'POST',
    body: formData,
  })
}

export async function submitManualResume(text: string, candidateId: string): Promise<ResumeDocumentResponse> {
  return apiRequest<ResumeDocumentResponse>('/api/resumes/manual', {
    method: 'POST',
    body: JSON.stringify({ text, candidate_id: candidateId }),
  })
}

export async function getResume(id: string): Promise<ResumeDocumentResponse> {
  return apiRequest<ResumeDocumentResponse>(`/api/resumes/${id}`)
}
