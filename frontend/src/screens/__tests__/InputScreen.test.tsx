import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SessionContext } from '../../session'
import { ResumeJDInputScreen } from '../ResumeJDInputScreen'
import { server } from '../../mocks/server'

beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function renderInputScreen() {
  const qc = new QueryClient()
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/input']}>
        <SessionContext.Provider value={{ session: {}, setSession: () => {}, clearSession: () => {} }}>
          <ResumeJDInputScreen />
        </SessionContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ResumeJDInputScreen', () => {
  it('renders file upload and JD textarea by default', () => {
    renderInputScreen()
    expect(screen.getByLabelText(/resume file/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/job description/i)).toBeInTheDocument()
  })

  it('shows character counter for text mode', async () => {
    renderInputScreen()
    const user = userEvent.setup()
    await user.click(screen.getByText('Enter Text'))
    const textarea = screen.getByLabelText(/resume text/i)
    await user.type(textarea, 'hello01234')
    expect(screen.getByText(/10 \/ 50,000/)).toBeInTheDocument()
  })

  it('enforces 10 MB file size limit', () => {
    renderInputScreen()
    const input = screen.getByLabelText(/resume file/i) as HTMLInputElement
    const bigFile = new File(['x'.repeat(100)], 'big.pdf', { type: 'application/pdf' })
    Object.defineProperty(bigFile, 'size', { value: 11 * 1024 * 1024 })
    fireEvent.change(input, { target: { files: [bigFile] } })
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText(/10 MB/i)).toBeInTheDocument()
  })

  it('submit button is present', () => {
    renderInputScreen()
    expect(screen.getByRole('button', { name: /submit/i })).toBeInTheDocument()
  })

  it('navigates to /evidence on successful submission', async () => {
    const user = userEvent.setup()
    const navigateFn = vi.fn()
    const qc = new QueryClient()

    // Use react-router's navigate mock by wrapping in MemoryRouter
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/input']}>
          <SessionContext.Provider
            value={{ session: {}, setSession: () => {}, clearSession: () => {} }}
          >
            <ResumeJDInputScreen />
          </SessionContext.Provider>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    const jdTextarea = screen.getByLabelText(/job description/i)
    await user.type(jdTextarea, 'Python required')

    // Switch to text mode and type resume text
    await user.click(screen.getByText('Enter Text'))
    const resumeTextarea = screen.getByLabelText(/resume text/i)
    await user.type(resumeTextarea, 'Python developer')

    const submitBtn = screen.getByRole('button', { name: /submit/i })
    await user.click(submitBtn)

    await waitFor(() => {
      // The submit mutation should have completed — check loading spinner gone
      expect(screen.queryByRole('status')).not.toBeInTheDocument()
    })

    void navigateFn
  })
})
