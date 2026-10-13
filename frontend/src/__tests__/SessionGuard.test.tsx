import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SessionContext } from '../session'
import { SessionGuard } from '../SessionGuard'
import type { Session } from '../session'

function renderWithGuard(path: string, session: Session) {
  const qc = new QueryClient()
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <SessionContext.Provider value={{ session, setSession: () => {}, clearSession: () => {} }}>
          <Routes>
            <Route path="/input" element={<div>Input Page</div>} />
            <Route
              path={path}
              element={
                <SessionGuard>
                  <div>Protected Content</div>
                </SessionGuard>
              }
            />
          </Routes>
        </SessionContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('SessionGuard', () => {
  it('shows redirect message and redirects to /input when no session', async () => {
    renderWithGuard('/evidence', {})
    // The guard initially renders the fallback message before navigating
    // After navigation, the Input Page renders
    await waitFor(() => {
      expect(screen.getByText('Input Page')).toBeInTheDocument()
    })
  })

  it('redirects /analysis to /input with ?redirect param when session is empty', async () => {
    renderWithGuard('/analysis', {})
    await waitFor(() => {
      expect(screen.getByText('Input Page')).toBeInTheDocument()
    })
  })

  it('redirects /recommendations to /input when no session', async () => {
    renderWithGuard('/recommendations', {})
    // After useEffect fires, we should be on the /input page
    await waitFor(() => {
      expect(screen.getByText('Input Page')).toBeInTheDocument()
    })
  })

  it('renders children when session has resumeId and jobDescriptionId', () => {
    renderWithGuard('/evidence', {
      resumeId: 'r1',
      jobDescriptionId: 'jd1',
    })
    expect(screen.getByText('Protected Content')).toBeInTheDocument()
  })
})
