import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/utils'
import UploadHistory from './UploadHistory'
import api, { apiClient } from '../../api/client'
import { useAppStore } from '../../store/appStore'

vi.mock('../../api/client', () => ({
  default: {
    get: vi.fn(),
    delete: vi.fn(),
  },
  apiClient: {
    getHistory: vi.fn(),
    parseFile: vi.fn(),
  },
}))

const mockHistory = {
  history: [
    {
      session_id: 'sid-active',
      created_at: '2026-02-01T10:00:00Z',
      total_value: 500000,
      total_invested: 400000,
      num_funds: 10,
      statement_period: 'Jan 2026',
    },
    {
      session_id: 'sid-old',
      created_at: '2026-01-01T10:00:00Z',
      total_value: 450000,
      total_invested: 380000,
      num_funds: 9,
    },
  ],
}

describe('UploadHistory', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState({
      mfSessionId: 'sid-active',
      activeModule: 'mutual_funds',
    })
    vi.mocked(apiClient.getHistory).mockResolvedValue(mockHistory as any)
    vi.stubGlobal('confirm', vi.fn(() => true))
  })

  it('renders statement history timeline', async () => {
    renderWithProviders(<UploadHistory />)

    expect(await screen.findByText('Statement History')).toBeInTheDocument()
    expect(screen.getByText('ACTIVE')).toBeInTheDocument()
    expect(screen.getByText(/Import New CAS/i)).toBeInTheDocument()
  })

  it('toggles upload panel and shows dropzone', async () => {
    renderWithProviders(<UploadHistory />)
    await screen.findByText('Statement History')

    await userEvent.click(screen.getByRole('button', { name: /Import New CAS/i }))

    expect(screen.getByText(/Drag & drop your CAS PDF/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Hide Upload/i })).toBeInTheDocument()
  })

  it('restores a previous session on RESTORE click', async () => {
    renderWithProviders(<UploadHistory />)
    await screen.findByText('Statement History')

    await userEvent.click(screen.getByRole('button', { name: /^RESTORE$/i }))

    expect(useAppStore.getState().mfSessionId).toBe('sid-old')
  })

  it('runs comparison when COMPARE is clicked', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: {
        baseline_session: 'sid-old',
        current_session: 'sid-active',
        new_transactions: [
          { fund: 'HDFC Flexi Cap', type: 'Purchase', amount: 5000, units: 10 },
        ],
        deltas: { portfolio_value_change: 50000, xirr_shift: 1.2, organic_growth_by_fund: {} },
        active_funds: ['HDFC Flexi Cap'],
      },
    } as any)

    renderWithProviders(<UploadHistory />)
    await screen.findByText('Statement History')

    await userEvent.click(screen.getByRole('button', { name: /^COMPARE$/i }))

    expect(await screen.findByText('Ledger Reconciliation')).toBeInTheDocument()
    expect(api.get).toHaveBeenCalledWith('/history/compare/sid-old/vs/sid-active')
  })

  it('shows empty alert when no history exists', async () => {
    vi.mocked(apiClient.getHistory).mockResolvedValue({ history: [] } as any)

    renderWithProviders(<UploadHistory />)

    expect(await screen.findByText(/No historical uploads found/i)).toBeInTheDocument()
  })

  it('deletes a non-active session after confirm', async () => {
    vi.mocked(api.delete).mockResolvedValue({} as any)
    renderWithProviders(<UploadHistory />)
    await screen.findByText('Statement History')

    const deleteBtns = screen.getAllByRole('button').filter((b) =>
      b.querySelector('[data-testid="DeleteOutlineIcon"]')
    )
    await userEvent.click(deleteBtns[1])
    await waitFor(() => {
      expect(api.delete).toHaveBeenCalledWith('/history/sid-old')
    })
  })

  it('aborts delete when confirm is cancelled', async () => {
    vi.stubGlobal('confirm', vi.fn(() => false))
    renderWithProviders(<UploadHistory />)
    await screen.findByText('Statement History')
    const deleteBtns = screen.getAllByRole('button').filter((b) =>
      b.querySelector('[data-testid="DeleteOutlineIcon"]')
    )
    await userEvent.click(deleteBtns[0])
    expect(api.delete).not.toHaveBeenCalled()
  })

  it('alerts and clears session when active session is deleted', async () => {
    const alertSpy = vi.fn()
    vi.stubGlobal('alert', alertSpy)
    vi.mocked(api.delete).mockResolvedValue({} as any)
    renderWithProviders(<UploadHistory />)
    await screen.findByText('Statement History')

    const deleteBtns = screen.getAllByRole('button').filter((b) =>
      b.querySelector('[data-testid="DeleteOutlineIcon"]')
    )
    await userEvent.click(deleteBtns[0])
    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith(expect.stringMatching(/active session/i))
    })
  })

  it('alerts when delete API fails', async () => {
    const alertSpy = vi.fn()
    vi.stubGlobal('alert', alertSpy)
    vi.mocked(api.delete).mockRejectedValueOnce(new Error('boom'))
    renderWithProviders(<UploadHistory />)
    await screen.findByText('Statement History')
    const deleteBtns = screen.getAllByRole('button').filter((b) =>
      b.querySelector('[data-testid="DeleteOutlineIcon"]')
    )
    await userEvent.click(deleteBtns[1])
    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('Failed to delete session.')
    })
  })

  it('uploads a CAS PDF and switches session', async () => {
    vi.mocked(apiClient.parseFile).mockResolvedValue({
      session_id: 'sid-new',
      total_value: 1,
    } as any)
    vi.mocked(apiClient.getHistory)
      .mockResolvedValueOnce(mockHistory as any)
      .mockResolvedValueOnce({
        history: [
          ...mockHistory.history,
          { session_id: 'sid-new', created_at: '2026-03-01T10:00:00Z', total_value: 1, total_invested: 1, num_funds: 1 },
        ],
      } as any)

    renderWithProviders(<UploadHistory />)
    await screen.findByText('Statement History')
    await userEvent.click(screen.getByRole('button', { name: /Import New CAS/i }))

    const file = new File(['%PDF-1.4'], 'cas.pdf', { type: 'application/pdf' })
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    await userEvent.upload(input, file)

    expect(await screen.findByText('cas.pdf')).toBeInTheDocument()
    const pwd = screen.getByPlaceholderText(/Defaults to your PAN/i)
    await userEvent.type(pwd, 'secret')
    await userEvent.click(screen.getByRole('button', { name: /Analyse & Switch/i }))

    await waitFor(() => {
      expect(apiClient.parseFile).toHaveBeenCalledWith(file, 'secret', 'mutual_funds')
      expect(useAppStore.getState().mfSessionId).toBe('sid-new')
    })
  })

  it('shows upload error when parse fails', async () => {
    vi.mocked(apiClient.parseFile).mockRejectedValueOnce({
      response: { data: { detail: 'Bad PDF password' } },
    })
    renderWithProviders(<UploadHistory />)
    await screen.findByText('Statement History')
    await userEvent.click(screen.getByRole('button', { name: /Import New CAS/i }))
    const file = new File(['%PDF'], 'bad.pdf', { type: 'application/pdf' })
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    await userEvent.upload(input, file)
    await userEvent.click(await screen.findByRole('button', { name: /Analyse & Switch/i }))
    expect(await screen.findByText('Bad PDF password')).toBeInTheDocument()
  })

  it('compare view groups purchases/redemptions and toggles hide closed', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: {
        baseline_session: 'sid-old',
        current_session: 'sid-active',
        new_transactions: [
          { fund: 'HDFC Flexi Cap', type: 'Purchase', amount: 5000, units: 10 },
          { fund: 'HDFC Flexi Cap', type: 'Redemption', amount: 2000, units: -4 },
          { fund: 'Closed Fund', type: 'SIP', amount: 1000, units: 2 },
          { fund: 'Dividend Only', type: 'Dividend', amount: 100, units: 0 },
        ],
        deltas: {
          portfolio_value_change: 50000,
          xirr_shift: -1.2,
          organic_growth_by_fund: { 'HDFC Flexi Cap': 12000, 'Other Fund': 500 },
        },
        active_funds: ['HDFC Flexi Cap'],
      },
    } as any)

    renderWithProviders(<UploadHistory />)
    await screen.findByText('Statement History')
    await userEvent.click(screen.getByRole('button', { name: /^COMPARE$/i }))
    expect(await screen.findByText('Ledger Reconciliation')).toBeInTheDocument()
    expect(screen.getByText(/TOTAL BOUGHT/i)).toBeInTheDocument()
    expect(screen.getByText(/XIRR SHIFT/i)).toBeInTheDocument()

    const hideClosed = screen.getByLabelText(/Hide Closed/i)
    await userEvent.click(hideClosed)
    expect(hideClosed).toBeInTheDocument()
  })

  it('handles history fetch failure gracefully', async () => {
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.mocked(apiClient.getHistory).mockRejectedValueOnce(new Error('offline'))
    renderWithProviders(<UploadHistory />)
    await waitFor(() => {
      expect(errSpy).toHaveBeenCalled()
    })
    errSpy.mockRestore()
  })

  it('handles compare API failure and no-session early return', async () => {
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.mocked(api.get).mockRejectedValueOnce(new Error('compare down'))
    renderWithProviders(<UploadHistory />)
    await screen.findByText('Statement History')
    await userEvent.click(screen.getByRole('button', { name: /^COMPARE$/i }))
    await waitFor(() => expect(errSpy).toHaveBeenCalled())
    errSpy.mockRestore()

    useAppStore.setState({ mfSessionId: null as any })
    vi.mocked(api.get).mockClear()
    renderWithProviders(<UploadHistory />)
    await screen.findByText('Statement History')
    const compareBtns = screen.queryAllByRole('button', { name: /^COMPARE$/i })
    if (compareBtns[0]) await userEvent.click(compareBtns[0])
    expect(api.get).not.toHaveBeenCalled()
  })

  it('covers switch-in/out grouping, identical ledger, and N/A top gainer', async () => {
    vi.mocked(api.get).mockResolvedValueOnce({
      data: {
        baseline_session: 'sid-missing',
        current_session: 'sid-also-missing',
        new_transactions: [],
        deltas: {
          portfolio_value_change: -20000,
          xirr_shift: 0.5,
          organic_growth_by_fund: {},
        },
        active_funds: [],
      },
    } as any)

    renderWithProviders(<UploadHistory />)
    await screen.findByText('Statement History')
    await userEvent.click(screen.getByRole('button', { name: /^COMPARE$/i }))
    expect(await screen.findByText('Identical Ledger')).toBeInTheDocument()
    expect(screen.getByText('Cryptographic Delta Analysis')).toBeInTheDocument()
    expect(screen.getByText('N/A')).toBeInTheDocument()

    vi.mocked(api.get).mockResolvedValueOnce({
      data: {
        baseline_session: 'sid-old',
        current_session: 'sid-active',
        new_transactions: [
          { fund: 'Switch Fund', type: 'Switch Out', amount: 3000, units: -5 },
          { fund: 'Switch Fund', type: 'Switch In', amount: 3000, units: 5 },
          { fund: 'Closed Only', type: 'Purchase', amount: 1000, units: 2 },
        ],
        deltas: {
          portfolio_value_change: 1000,
          xirr_shift: 0,
          organic_growth_by_fund: { 'Switch Fund': -500 },
        },
        active_funds: ['Switch Fund'],
      },
    } as any)
    await userEvent.click(screen.getByRole('button', { name: /^COMPARE$/i }))
    expect(await screen.findByText(/TRANSACTION DELTAS/i)).toBeInTheDocument()

    // Hide closed keeps Closed Only out; toggling off reveals it
    await userEvent.click(screen.getByLabelText(/Hide Closed/i))
    expect(await screen.findByText(/Closed Only/i)).toBeInTheDocument()
  })

  it('shows all-transactions-hidden empty state and clears compare on delete', async () => {
    vi.mocked(api.get).mockResolvedValueOnce({
      data: {
        baseline_session: 'sid-old',
        current_session: 'sid-active',
        new_transactions: [
          { fund: 'Gone Fund', type: 'Redemption', amount: 500, units: -1 },
        ],
        deltas: { portfolio_value_change: 0, xirr_shift: 0, organic_growth_by_fund: {} },
        active_funds: ['Still Open'],
      },
    } as any)
    vi.mocked(api.delete).mockResolvedValue({} as any)

    renderWithProviders(<UploadHistory />)
    await screen.findByText('Statement History')
    await userEvent.click(screen.getByRole('button', { name: /^COMPARE$/i }))
    expect(await screen.findByText(/All Transactions Hidden/i)).toBeInTheDocument()

    const deleteBtns = screen.getAllByRole('button').filter((b) =>
      b.querySelector('[data-testid="DeleteOutlineIcon"]'),
    )
    await userEvent.click(deleteBtns[1])
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/history/sid-old'))
  })

  it('falls back to generic upload error when detail is missing', async () => {
    vi.mocked(apiClient.parseFile).mockRejectedValueOnce(new Error('plain fail'))
    renderWithProviders(<UploadHistory />)
    await screen.findByText('Statement History')
    await userEvent.click(screen.getByRole('button', { name: /Import New CAS/i }))
    const file = new File(['%PDF'], 'plain.pdf', { type: 'application/pdf' })
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    await userEvent.upload(input, file)
    await userEvent.click(await screen.findByRole('button', { name: /Analyse & Switch/i }))
    expect(await screen.findByText(/Failed to parse/i)).toBeInTheDocument()
  })
})
