import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { SessionContext } from '../../session'
import { CandidateEvidenceReviewScreen } from '../CandidateEvidenceReviewScreen'
import { server } from '../../mocks/server'

beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

const FAKE_CANDIDATE_ID = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
const FAKE_RESUME_ID = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
const FAKE_JD_ID = 'cccccccc-cccc-cccc-cccc-cccccccccccc'
const FAKE_FACT_ID = 'ffffffff-ffff-ffff-ffff-ffffffffffff'

const mockSession = {
  resumeId: FAKE_RESUME_ID,
  candidateId: FAKE_CANDIDATE_ID,
  jobDescriptionId: FAKE_JD_ID,
}

function renderEvidenceScreen() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <SessionContext.Provider
          value={{ session: mockSession, setSession: () => {}, clearSession: () => {} }}
        >
          <CandidateEvidenceReviewScreen />
        </SessionContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('CandidateEvidenceReviewScreen', () => {
  it('renders fact cards', async () => {
    server.use(
      http.get('/api/candidates/:candidateId/evidence', () =>
        HttpResponse.json({
          data: {
            candidate_id: FAKE_CANDIDATE_ID,
            facts: [
              {
                id: FAKE_FACT_ID,
                candidate_id: FAKE_CANDIDATE_ID,
                claim_text: 'Built Python APIs',
                original_claim_text: 'Built Python APIs',
                claim_type: 'skill',
                source_document_id: FAKE_RESUME_ID,
                source_span: { start: 0, end: 18 },
                verification_status: 'Needs Confirmation',
                metadata: {},
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString(),
              },
            ],
          },
        }),
      ),
    )

    renderEvidenceScreen()
    await waitFor(() => {
      expect(screen.getByText('Built Python APIs')).toBeInTheDocument()
    })
    // Check the badge (not the select option)
    const badges = screen.getAllByText('Needs Confirmation')
    expect(badges.length).toBeGreaterThan(0)
  })

  it('inline edit save calls patch', async () => {
    server.use(
      http.get('/api/candidates/:candidateId/evidence', () =>
        HttpResponse.json({
          data: {
            candidate_id: FAKE_CANDIDATE_ID,
            facts: [
              {
                id: FAKE_FACT_ID,
                candidate_id: FAKE_CANDIDATE_ID,
                claim_text: 'Python developer',
                original_claim_text: 'Python developer',
                claim_type: 'skill',
                source_document_id: FAKE_RESUME_ID,
                source_span: { start: 0, end: 16 },
                verification_status: 'Needs Confirmation',
                metadata: {},
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString(),
              },
            ],
          },
        }),
      ),
    )

    let patchCalled = false
    server.use(
      http.patch('/api/candidates/:candidateId/evidence/:factId', () => {
        patchCalled = true
        return HttpResponse.json({
          data: {
            id: FAKE_FACT_ID,
            candidate_id: FAKE_CANDIDATE_ID,
            claim_text: 'Python developer',
            original_claim_text: 'Python developer',
            claim_type: 'skill',
            source_document_id: FAKE_RESUME_ID,
            source_span: { start: 0, end: 16 },
            verification_status: 'Supported',
            metadata: {},
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          },
        })
      }),
    )

    renderEvidenceScreen()
    await waitFor(() => screen.getByText('Python developer'))

    const user = userEvent.setup()
    const saveBtn = screen.getByRole('button', { name: /save/i })
    await user.click(saveBtn)

    await waitFor(() => {
      expect(patchCalled).toBe(true)
    })
  })

  it('Continue button is present', async () => {
    renderEvidenceScreen()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /continue to analysis/i })).toBeInTheDocument()
    })
  })
})
