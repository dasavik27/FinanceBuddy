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
})
