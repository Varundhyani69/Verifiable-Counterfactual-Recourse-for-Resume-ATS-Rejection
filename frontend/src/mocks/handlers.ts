import { http, HttpResponse } from 'msw'

const FAKE_RESUME_ID = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
const FAKE_CANDIDATE_ID = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
const FAKE_JD_ID = 'cccccccc-cccc-cccc-cccc-cccccccccccc'
const FAKE_VERSION_ID = 'dddddddd-dddd-dddd-dddd-dddddddddddd'
const FAKE_RECOURSE_ID = 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'

export const handlers = [
  http.post('/api/resumes/manual', () => {
    return HttpResponse.json({
      data: {
        id: FAKE_RESUME_ID,
        candidate_id: FAKE_CANDIDATE_ID,
        document_type: 'manual',
        extracted_text: 'Python developer',
        filename: null,
        source_spans: [],
        created_at: new Date().toISOString(),
      },
    }, { status: 201 })
  }),

  http.post('/api/resumes/upload', () => {
    return HttpResponse.json({
      data: {
        id: FAKE_RESUME_ID,
        candidate_id: FAKE_CANDIDATE_ID,
        document_type: 'pdf',
        extracted_text: 'Uploaded resume content',
        filename: 'resume.pdf',
        source_spans: [],
        created_at: new Date().toISOString(),
      },
    }, { status: 201 })
  }),

  http.get('/api/resumes/:id', () => {
    return HttpResponse.json({
      data: {
        id: FAKE_RESUME_ID,
        candidate_id: FAKE_CANDIDATE_ID,
        document_type: 'manual',
        extracted_text: 'Python developer',
        filename: null,
        source_spans: [],
        created_at: new Date().toISOString(),
      },
    })
  }),

  http.post('/api/job-descriptions', () => {
    return HttpResponse.json({
      data: {
        id: FAKE_JD_ID,
        raw_text: 'Python required',
        requirements: [],
        warning: null,
        created_at: new Date().toISOString(),
      },
    }, { status: 201 })
  }),

  http.get('/api/candidates/:candidateId/evidence', () => {
    return HttpResponse.json({
      data: {
        candidate_id: FAKE_CANDIDATE_ID,
        facts: [],
      },
    })
  }),

  http.patch('/api/candidates/:candidateId/evidence/:factId', () => {
    return HttpResponse.json({
      data: {
        id: 'ffffffff-ffff-ffff-ffff-ffffffffffff',
        candidate_id: FAKE_CANDIDATE_ID,
        claim_text: 'Updated claim',
        original_claim_text: 'Original claim',
        claim_type: 'skill',
        source_document_id: FAKE_RESUME_ID,
        source_span: { start: 0, end: 10 },
        verification_status: 'Supported',
        metadata: {},
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    })
  }),

  http.post('/api/analysis', () => {
    return HttpResponse.json({
      data: {
        resume_version_id: FAKE_VERSION_ID,
        version_number: 1,
        score_breakdown: {
          total_score: 0.72,
          skill_overlap_score: 0.6,
          semantic_similarity_score: 0.84,
          weights: { skill_overlap: 0.5, sbert: 0.5 },
          threshold: 0.5,
        },
        decision: 'pass',
        disclosure: 'This score is produced by a simulated model and does not predict any employer\'s hiring decision.',
      },
    }, { status: 201 })
  }),

  http.post('/api/recourse/generate', () => {
    return HttpResponse.json({
      data: {
        recourse_id: FAKE_RECOURSE_ID,
        status: 'feasible',
        accepted_edits: [
          {
            edit_id: 'edit-0001-0000-0000-000000000001',
            prose_description: 'Add Python experience to demonstrate alignment with job requirements.',
            ats_improvement_reason: 'The job requires Python; adding it improves skill overlap score.',
            original_text: 'Developed software solutions.',
            proposed_text: 'Developed Python-based software solutions.',
            edit_type: 'rephrase',
            evidence_fact_ids: [],
            evidence_claim_texts: [],
            job_requirement_ids: [],
            requirement_texts: [],
            verification_status: 'Needs Confirmation',
            edit_cost: 0.2,
            score_contribution: 0.15,
            can_confirm: true,
            can_reject: true,
          },
        ],
        total_edit_cost: 0.2,
        projected_score: 0.87,
        projected_decision: 'pass',
      },
    }, { status: 201 })
  }),

  http.post('/api/recourse/:resumeVersionId/verify', () => {
    return HttpResponse.json({
      data: {
        resume_version_id: FAKE_VERSION_ID,
        verification_reports: [],
      },
    })
  }),

  http.patch('/api/recourse/edits/:editId/status', () => {
    return HttpResponse.json({
      data: {
        edit_id: 'ffffffff-ffff-ffff-ffff-ffffffffffff',
        verification_status: 'Supported',
        action_applied: 'confirm',
      },
    })
  }),

  http.post('/api/experiments', () => {
    return HttpResponse.json({
      data: {
        id: 'ffffffff-ffff-ffff-ffff-ffffffffffff',
        resume_id: FAKE_RESUME_ID,
        job_description_id: FAKE_JD_ID,
        model_configuration: {},
        baseline_method: 'original_resume',
        original_score: 0.4,
        final_score: 0.72,
        threshold: 0.5,
        decision_flipped: true,
        total_edit_cost: 0.3,
        grounding_metrics: {},
        random_seed: null,
        created_at: new Date().toISOString(),
      },
    }, { status: 201 })
  }),

  http.get('/api/experiments/:id', () => {
    return HttpResponse.json({
      data: {
        id: 'ffffffff-ffff-ffff-ffff-ffffffffffff',
        resume_id: FAKE_RESUME_ID,
        job_description_id: FAKE_JD_ID,
        model_configuration: {},
        baseline_method: 'original_resume',
        original_score: 0.4,
        final_score: 0.72,
        threshold: 0.5,
        decision_flipped: true,
        total_edit_cost: 0.3,
        grounding_metrics: {},
        random_seed: null,
        created_at: new Date().toISOString(),
      },
    })
  }),

  // Additional endpoints (14 total to match spec requirement)
  http.get('/api/job-descriptions/:id', () => {
    return HttpResponse.json({
      data: {
        id: FAKE_JD_ID,
        raw_text: 'Python required',
        requirements: [],
        warning: null,
        created_at: new Date().toISOString(),
      },
    })
  }),

  http.get('/api/experiments/:id/report', () => {
    return HttpResponse.json({
      data: {
        id: 'ffffffff-ffff-ffff-ffff-ffffffffffff',
        resume_id: FAKE_RESUME_ID,
        job_description_id: FAKE_JD_ID,
        model_configuration: {},
        baseline_method: 'original_resume',
        original_score: 0.4,
        final_score: 0.72,
        threshold: 0.5,
        decision_flipped: true,
        total_edit_cost: 0.3,
        grounding_metrics: {},
        random_seed: null,
        created_at: new Date().toISOString(),
      },
    })
  }),
]
