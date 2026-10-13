import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SessionContext } from '../../session'
import { ATSAnalysisScreen } from '../ATSAnalysisScreen'
import { server } from '../../mocks/server'
import type { AnalysisResponse } from '../../types/analysis'

beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

const mockAnalysisResult: AnalysisResponse = {
  resume_version_id: 'dddddddd-dddd-dddd-dddd-dddddddddddd',
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
}

function renderAnalysisScreen(analysisResult: AnalysisResponse | undefined) {
  const qc = new QueryClient()
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <SessionContext.Provider
          value={{
            session: {
              resumeId: 'r1',
              jobDescriptionId: 'jd1',
              resumeVersionId: 'rv1',
              analysisResult,
            },
            setSession: () => {},
            clearSession: () => {},
          }}
        >
          <ATSAnalysisScreen />
        </SessionContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ATSAnalysisScreen', () => {
  it('renders total score and decision badge', () => {
    renderAnalysisScreen(mockAnalysisResult)
    expect(screen.getByText('72%')).toBeInTheDocument()
    expect(screen.getByText('PASS')).toBeInTheDocument()
  })

  it('shows disclosure string', () => {
    renderAnalysisScreen(mockAnalysisResult)
    expect(screen.getByText(/simulated model/i)).toBeInTheDocument()
  })

  it('renders generate recommendations button', () => {
    renderAnalysisScreen(mockAnalysisResult)
    expect(
      screen.getByRole('button', { name: /generate recommendations/i }),
    ).toBeInTheDocument()
  })

  it('shows error when no analysis result', () => {
    renderAnalysisScreen(undefined)
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText(/no analysis result/i)).toBeInTheDocument()
  })
})
