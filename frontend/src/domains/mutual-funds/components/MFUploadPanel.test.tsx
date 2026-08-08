import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/utils'
import MFUploadPanel, { SwitchStatementButton } from './MFUploadPanel'
import { apiClient } from '../../../shared/api/client'
import { useAppStore } from '../../../shared/store/appStore'

vi.mock('../../../shared/api/client', () => ({
  apiClient: {
    getHistory: vi.fn(),
    parseFile: vi.fn(),
    deleteSession: vi.fn(),
  },
}))

describe('MFUploadPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState({
      mfSessionId: null,
      pan: 'ABCDE1234F',
      userId: 'user-1',
      activeModule: 'mutual_funds',
    })
    vi.mocked(apiClient.getHistory).mockResolvedValue({
      history: [
        {
          session_id: 'mf-sess-1',
          filename: 'cams_cas.pdf',
          created_at: '2024-01-01T10:00:00Z',
          total_value: 500000,
          num_funds: 5,
          statement_period: 'Jan 2024',
        },
      ],
    } as any)
  })

  it('renders upload panel with history restore', async () => {
    const user = userEvent.setup()
    renderWithProviders(<MFUploadPanel />)

    expect(screen.getByText('MUTUAL FUNDS PORTFOLIO')).toBeInTheDocument()
    expect(await screen.findByText('Welcome back — pick up where you left off')).toBeInTheDocument()
    expect(screen.getByText('Previous Statements')).toBeInTheDocument()
    expect(screen.getByText('Period: Jan 2024')).toBeInTheDocument()
    expect(screen.getByText('₹5,00,000')).toBeInTheDocument()

    // Restore a previous session via history row click
    await user.click(screen.getByText('Period: Jan 2024'))
    await waitFor(() => {
      expect(useAppStore.getState().mfSessionId).toBe('mf-sess-1')
    })
  })

  it('renders empty import hero when there is no history', async () => {
    vi.mocked(apiClient.getHistory).mockResolvedValue({ history: [] } as any)
    renderWithProviders(<MFUploadPanel />)

    expect(await screen.findByText('Import Your CAS Statement')).toBeInTheDocument()
    expect(screen.getByText('Upload CAS PDF')).toBeInTheDocument()
    expect(screen.queryByText('Previous Statements')).not.toBeInTheDocument()
  })
  it('skips history fetch when PAN is missing', async () => {
    useAppStore.setState({ pan: null })
    renderWithProviders(<MFUploadPanel />)
    expect(await screen.findByText('Import Your CAS Statement')).toBeInTheDocument()
    expect(apiClient.getHistory).not.toHaveBeenCalled()
  })

  it('uploads a CAS PDF and analyses the portfolio', async () => {
    const user = userEvent.setup()
    vi.mocked(apiClient.parseFile).mockResolvedValue({
      session_id: 'mf-new-sess',
      total_value: 750000,
    } as any)

    const { container } = renderWithProviders(<MFUploadPanel />)
    expect(await screen.findByText(/Welcome back/i)).toBeInTheDocument()

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['%PDF-1.4 cas'], 'statement.pdf', { type: 'application/pdf' })
    await user.upload(fileInput, file)

    expect(await screen.findByText('statement.pdf')).toBeInTheDocument()

    const password = screen.getByPlaceholderText(/Defaults to your PAN/i)
    await user.type(password, 'abcde1234f')

    await user.click(screen.getByRole('button', { name: /Analyse Portfolio/i }))

    await waitFor(() => {
      expect(apiClient.parseFile).toHaveBeenCalledWith(file, 'abcde1234f', 'mutual_funds')
    })
    expect(useAppStore.getState().mfSessionId).toBe('mf-new-sess')
    expect(useAppStore.getState().pan).toBe('ABCDE1234F')
  })

  it('shows parse error from API detail', async () => {
    const user = userEvent.setup()
    vi.mocked(apiClient.parseFile).mockRejectedValue({
      response: { data: { detail: 'Incorrect PDF password' } },
    })

    const { container } = renderWithProviders(<MFUploadPanel />)
    expect(await screen.findByText(/Welcome back/i)).toBeInTheDocument()

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['bad'], 'bad.pdf', { type: 'application/pdf' })
    await user.upload(fileInput, file)

    await user.click(await screen.findByRole('button', { name: /Analyse Portfolio/i }))
    expect(await screen.findByText('Incorrect PDF password')).toBeInTheDocument()
  })

  it('shows generic parse error when detail is missing', async () => {
    const user = userEvent.setup()
    vi.mocked(apiClient.parseFile).mockRejectedValue(new Error('boom'))

    const { container } = renderWithProviders(<MFUploadPanel />)
    expect(await screen.findByText(/Welcome back/i)).toBeInTheDocument()

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(fileInput, new File(['x'], 'x.pdf', { type: 'application/pdf' }))
    await user.click(await screen.findByRole('button', { name: /Analyse Portfolio/i }))
    expect(await screen.findByText(/Failed to parse/i)).toBeInTheDocument()
  })

  it('renders switch statement button when session exists', async () => {
    renderWithProviders(<SwitchStatementButton sessionId="mf-sess-1" />)
    expect(screen.getByText('Switch Statement')).toBeInTheDocument()
  })

  it('opens switch popover, restores history, and uploads via mini dropzone', async () => {
    const user = userEvent.setup()
    useAppStore.setState({ mfSessionId: 'mf-sess-1', pan: 'ABCDE1234F' })
    vi.mocked(apiClient.parseFile).mockResolvedValue({
      session_id: 'mf-from-mini',
      total_value: 100000,
    } as any)

    renderWithProviders(<SwitchStatementButton sessionId="mf-sess-1" />)

    await user.click(screen.getByRole('button', { name: /Switch portfolio statement/i }))
    expect(await screen.findByText('Portfolio Statements')).toBeInTheDocument()
    expect(await screen.findByText('Period: Jan 2024')).toBeInTheDocument()
    expect(screen.getByText(/5 Funds/i)).toBeInTheDocument()

    // Popover content is portaled to document.body
    const miniInput = await waitFor(() => {
      const inputs = document.querySelectorAll('input[type="file"]')
      expect(inputs.length).toBeGreaterThan(0)
      return inputs[inputs.length - 1] as HTMLInputElement
    })
    const file = new File(['%PDF'], 'new_cas.pdf', { type: 'application/pdf' })
    await user.upload(miniInput, file)

    expect(await screen.findByText('new_cas.pdf')).toBeInTheDocument()
    const pw = screen.getByPlaceholderText(/Defaults to PAN if blank/i)
    await user.type(pw, 'xyzpan99')

    await user.click(screen.getByRole('button', { name: /Import & Analyse/i }))
    await waitFor(() => {
      expect(apiClient.parseFile).toHaveBeenCalledWith(file, 'xyzpan99', 'mutual_funds')
    })
    expect(useAppStore.getState().mfSessionId).toBe('mf-from-mini')
  })

  it('surfaces mini-dropzone upload errors', async () => {
    const user = userEvent.setup()
    useAppStore.setState({ mfSessionId: 'mf-sess-1', pan: 'ABCDE1234F' })
    vi.mocked(apiClient.parseFile).mockRejectedValue({
      response: { data: { detail: 'CAS parse failed' } },
    })

    renderWithProviders(<SwitchStatementButton sessionId="mf-sess-1" />)
    await user.click(screen.getByRole('button', { name: /Switch portfolio statement/i }))
    expect(await screen.findByText('Import New Statement')).toBeInTheDocument()

    const miniInput = await waitFor(() => {
      const inputs = document.querySelectorAll('input[type="file"]')
      expect(inputs.length).toBeGreaterThan(0)
      return inputs[inputs.length - 1] as HTMLInputElement
    })
    await user.upload(miniInput, new File(['x'], 'fail.pdf', { type: 'application/pdf' }))
    await user.click(await screen.findByRole('button', { name: /Import & Analyse/i }))
    expect(await screen.findByText('CAS parse failed')).toBeInTheDocument()
  })

  it('handles history fetch failure for switch button without crashing', async () => {
    const user = userEvent.setup()
    useAppStore.setState({ mfSessionId: 'mf-sess-1', pan: 'ABCDE1234F' })
    vi.mocked(apiClient.getHistory).mockRejectedValue(new Error('history down'))

    renderWithProviders(<SwitchStatementButton sessionId="mf-sess-1" />)
    await user.click(screen.getByRole('button', { name: /Switch portfolio statement/i }))
    expect(await screen.findByText('Portfolio Statements')).toBeInTheDocument()
  })

  it('returns empty history when switch button has no PAN', async () => {
    const user = userEvent.setup()
    useAppStore.setState({ mfSessionId: 'mf-sess-1', pan: null })
    renderWithProviders(<SwitchStatementButton sessionId="mf-sess-1" />)
    await user.click(screen.getByRole('button', { name: /Switch portfolio statement/i }))
    expect(await screen.findByText('Portfolio Statements')).toBeInTheDocument()
    expect(apiClient.getHistory).not.toHaveBeenCalled()
  })

  it('renders history rows without statement_period badges', async () => {
    vi.mocked(apiClient.getHistory).mockResolvedValue({
      history: [
        {
          session_id: 'mf-sess-2',
          filename: 'no_period.pdf',
          created_at: '2024-02-01T10:00:00Z',
          total_value: 250000,
          num_funds: 3,
        },
      ],
    } as any)

    renderWithProviders(<MFUploadPanel />)
    expect(await screen.findByText('Previous Statements')).toBeInTheDocument()
    expect(screen.queryByText(/Period:/i)).not.toBeInTheDocument()
    expect(screen.getByText('₹2,50,000')).toBeInTheDocument()
  })

  it('uploads without password and skips identity update', async () => {
    const user = userEvent.setup()
    useAppStore.setState({ pan: 'OLDPPAN12F' })
    vi.mocked(apiClient.parseFile).mockResolvedValue({
      session_id: 'mf-nopw',
      total_value: 100000,
    } as any)

    const { container } = renderWithProviders(<MFUploadPanel />)
    expect(await screen.findByText(/Welcome back/i)).toBeInTheDocument()

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(fileInput, new File(['%PDF'], 'plain.pdf', { type: 'application/pdf' }))
    await user.click(await screen.findByRole('button', { name: /Analyse Portfolio/i }))

    await waitFor(() => {
      expect(apiClient.parseFile).toHaveBeenCalledWith(expect.any(File), '', 'mutual_funds')
    })
    expect(useAppStore.getState().mfSessionId).toBe('mf-nopw')
    expect(useAppStore.getState().pan).toBe('OLDPPAN12F')
  })

  it('logs and recovers when main panel history fetch fails', async () => {
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.mocked(apiClient.getHistory).mockRejectedValue(new Error('history boom'))
    renderWithProviders(<MFUploadPanel />)
    expect(await screen.findByText('Import Your CAS Statement')).toBeInTheDocument()
    await waitFor(() => expect(errSpy).toHaveBeenCalled())
    errSpy.mockRestore()
  })

  it('mini-dropzone uploads without password and shows generic error', async () => {
    const user = userEvent.setup()
    useAppStore.setState({ mfSessionId: 'mf-sess-1', pan: 'ABCDE1234F' })
    vi.mocked(apiClient.parseFile).mockResolvedValue({
      session_id: 'mf-mini-nopw',
      total_value: 50000,
    } as any)

    renderWithProviders(<SwitchStatementButton sessionId="mf-sess-1" />)
    await user.click(screen.getByRole('button', { name: /Switch portfolio statement/i }))
    expect(await screen.findByText('Import New Statement')).toBeInTheDocument()

    const miniInput = await waitFor(() => {
      const inputs = document.querySelectorAll('input[type="file"]')
      expect(inputs.length).toBeGreaterThan(0)
      return inputs[inputs.length - 1] as HTMLInputElement
    })
    await user.upload(miniInput, new File(['%PDF'], 'mini.pdf', { type: 'application/pdf' }))
    await user.click(await screen.findByRole('button', { name: /Import & Analyse/i }))
    await waitFor(() => {
      expect(apiClient.parseFile).toHaveBeenCalledWith(expect.any(File), '', 'mutual_funds')
    })
    expect(useAppStore.getState().mfSessionId).toBe('mf-mini-nopw')
  })

  it('switch history without statement_period still lists funds', async () => {
    const user = userEvent.setup()
    useAppStore.setState({ mfSessionId: 'mf-sess-1', pan: 'ABCDE1234F' })
    vi.mocked(apiClient.getHistory).mockResolvedValue({
      history: [
        {
          session_id: 'mf-sess-3',
          filename: 'bare.pdf',
          created_at: '2024-03-01T10:00:00Z',
          total_value: 100000,
          num_funds: 2,
        },
      ],
    } as any)

    renderWithProviders(<SwitchStatementButton sessionId="mf-sess-1" />)
    await user.click(screen.getByRole('button', { name: /Switch portfolio statement/i }))
    expect(await screen.findByText(/2 Funds/i)).toBeInTheDocument()
    expect(screen.queryByText(/Period:/i)).not.toBeInTheDocument()
  })

  it('mini-dropzone shows generic parse error when detail missing', async () => {
    const user = userEvent.setup()
    useAppStore.setState({ mfSessionId: 'mf-sess-1', pan: 'ABCDE1234F' })
    vi.mocked(apiClient.parseFile).mockRejectedValue(new Error('network'))

    renderWithProviders(<SwitchStatementButton sessionId="mf-sess-1" />)
    await user.click(screen.getByRole('button', { name: /Switch portfolio statement/i }))

    const miniInput = await waitFor(() => {
      const inputs = document.querySelectorAll('input[type="file"]')
      expect(inputs.length).toBeGreaterThan(0)
      return inputs[inputs.length - 1] as HTMLInputElement
    })
    await user.upload(miniInput, new File(['x'], 'fail2.pdf', { type: 'application/pdf' }))
    await user.click(await screen.findByRole('button', { name: /Import & Analyse/i }))
    expect(await screen.findByText(/Failed to parse/i)).toBeInTheDocument()
  })
})
