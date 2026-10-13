export interface ResumeDocumentResponse {
  id: string
  candidate_id: string
  filename: string | null
  document_type: string
  extracted_text: string
  source_spans: Array<Record<string, number | string>>
  created_at: string
}

export interface JobDescriptionResponse {
  id: string
  raw_text: string
  requirements: unknown[]
  warning: string | null
  created_at: string
}
