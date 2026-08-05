import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
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
    useAppStore.setState({ mfSessionId: null, pan: 'ABCDE1234F', activeModule: 'mutual_funds' })
    vi.mocked(apiClient.getHistory).mockResolvedValue({
      history: [
        { session_id: 'mf-sess-1', filename: 'cams_cas.pdf', created_at: '2024-01-01', total_value: 500000, fund_count: 5, statement_period: 'Jan 2024' },
      ],
    } as any)
  })

  it('renders upload panel with history restore', async () => {
    renderWithProviders(<MFUploadPanel />)

    expect(screen.getByText('MUTUAL FUNDS PORTFOLIO')).toBeInTheDocument()
    expect(await screen.findByText('Welcome back — pick up where you left off')).toBeInTheDocument()
    expect(screen.getByText('Previous Statements')).toBeInTheDocument()
    expect(screen.getByText('Period: Jan 2024')).toBeInTheDocument()
    expect(screen.getByText('₹5,00,000')).toBeInTheDocument()
  })

  it('renders switch statement button when session exists', async () => {
    renderWithProviders(<SwitchStatementButton sessionId="mf-sess-1" />)
    expect(screen.getByText('Switch Statement')).toBeInTheDocument()
  })
})
