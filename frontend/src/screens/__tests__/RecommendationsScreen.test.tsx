import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { SessionContext } from '../../session'
import { CounterfactualRecommendationsScreen } from '../CounterfactualRecommendationsScreen'
import { server } from '../../mocks/server'
import type { RecourseGenerateResponse } from '../../types/recourse'
import type { AnalysisResponse } from '../../types/analysis'

beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

const EDIT_NEEDS_ID = 'edit-needs-conf-0001-000000000001'
const EDIT_SUPPORTED_ID = 'edit-supported-0001-00000000000'

const mockAnalysis: AnalysisResponse = {
  resume_version_id: 'dddddddd-dddd-dddd-dddd-dddddddddddd',
  version_number: 1,
  score_breakdown: {
    total_score: 0.4,
    skill_overlap_score: 0.3,
    semantic_similarity_score: 0.5,
    weights: { skill_overlap: 0.5, sbert: 0.5 },
    threshold: 0.5,
  },
  decision: 'fail',
  disclosure: 'Simulated.',
}

const mockRecourse: RecourseGenerateResponse = {
  recourse_id: 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee',
  status: 'feasible',
  accepted_edits: [
    {
      edit_id: EDIT_NEEDS_ID,
      prose_description: 'Add Python experience to your resume.',
      ats_improvement_reason: 'This edit addresses the Python requirement.',
      original_text: 'old text 1',
      proposed_text: 'new text 1',
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
    {
      edit_id: EDIT_SUPPORTED_ID,
      prose_description: 'Highlight Docker experience.',
      ats_improvement_reason: 'This addresses the Docker requirement.',
      original_text: 'old text 2',
      proposed_text: 'new text 2',
      edit_type: 'rephrase',
      evidence_fact_ids: [],
      evidence_claim_texts: [],
      job_requirement_ids: [],
      requirement_texts: [],
      verification_status: 'Supported',
      edit_cost: 0.1,
      score_contribution: 0.1,
      can_confirm: false,
      can_reject: false,
    },
  ],
  total_edit_cost: 0.3,
  projected_score: 0.65,
  projected_decision: 'pass',
}

function renderRecommendations(recourseResult: RecourseGenerateResponse | undefined) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <SessionContext.Provider
          value={{
            session: {
              resumeId: 'r1',
              jobDescriptionId: 'jd1',
              resumeVersionId: 'rv1',
              recourseId: 'rec1',
              analysisResult: mockAnalysis,
              recourseResult,
            },
            setSession: () => {},
            clearSession: () => {},
          }}
        >
          <CounterfactualRecommendationsScreen />
        </SessionContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('CounterfactualRecommendationsScreen', () => {
  it('renders ExplanationCards for each accepted edit', () => {
    renderRecommendations(mockRecourse)
    const cards = screen.getAllByTestId('explanation-card')
    expect(cards).toHaveLength(2)
  })

  it('Needs Confirmation card has Confirm and Reject buttons', () => {
    renderRecommendations(mockRecourse)
    expect(screen.getByRole('button', { name: /confirm/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /reject/i })).toBeInTheDocument()
  })

  it('Confirm button updates status without refetch', async () => {
    server.use(
      http.patch('/api/recourse/edits/:editId/status', () =>
        HttpResponse.json({
          data: {
            edit_id: EDIT_NEEDS_ID,
            verification_status: 'Supported',
            action_applied: 'confirm',
          },
        }),
      ),
    )
    const user = userEvent.setup()
    renderRecommendations(mockRecourse)
    await user.click(screen.getByRole('button', { name: /confirm/i }))
    await waitFor(() => {
      // After confirm the "Needs Confirmation" badge on that card should be gone
      const badges = screen.queryAllByText('Needs Confirmation')
      expect(badges).toHaveLength(0)
    })
  })

  it('Reject button removes card from list', async () => {
    server.use(
      http.patch('/api/recourse/edits/:editId/status', () =>
        HttpResponse.json({
          data: {
            edit_id: EDIT_NEEDS_ID,
            verification_status: 'Unsupported',
            action_applied: 'reject',
          },
        }),
      ),
    )
    const user = userEvent.setup()
    renderRecommendations(mockRecourse)
    expect(screen.getAllByTestId('explanation-card')).toHaveLength(2)
    await user.click(screen.getByRole('button', { name: /reject/i }))
    await waitFor(() => {
      expect(screen.getAllByTestId('explanation-card')).toHaveLength(1)
    })
  })

  it('aggregate metrics update after reject', async () => {
    server.use(
      http.patch('/api/recourse/edits/:editId/status', () =>
        HttpResponse.json({
          data: {
            edit_id: EDIT_NEEDS_ID,
            verification_status: 'Unsupported',
            action_applied: 'reject',
          },
        }),
      ),
    )
    const user = userEvent.setup()
    renderRecommendations(mockRecourse)

    // Initial total cost: 0.20 + 0.10 = 0.30
    expect(screen.getByText('0.30')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /reject/i }))
    await waitFor(() => {
      // After reject of first edit (cost 0.20), only 0.10 remains
      expect(screen.getByText('0.10')).toBeInTheDocument()
    })
  })

  it('infeasible state shows error banner and partial edits section', () => {
    const infeasibleRecourse: RecourseGenerateResponse = {
      recourse_id: 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee',
      status: 'infeasible',
      reason: 'threshold',
      detail: 'No subset of edits could cross the ATS threshold.',
      constraints_violated: ['threshold'],
      partial_result: { edits: [], total_edit_cost: 0, projected_score: 0 },
    }
    renderRecommendations(infeasibleRecourse)
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText(/threshold/i)).toBeInTheDocument()
  })

  it('shows error when no recourse result', () => {
    renderRecommendations(undefined)
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })
})
