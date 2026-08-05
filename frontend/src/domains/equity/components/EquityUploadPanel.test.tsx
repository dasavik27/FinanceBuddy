import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/utils'
import EquityUploadPanel, { SwitchEquityStatementButton } from './EquityUploadPanel'
import { apiClient } from '../../../shared/api/client'
import { useAppStore } from '../../../shared/store/appStore'

vi.mock('../../../shared/api/client', () => ({
  apiClient: {
    getEquityHistory: vi.fn(),
    deleteHistorySession: vi.fn(),
    parseEquityCsv: vi.fn(),
    getKiteLoginUrl: vi.fn(),
    connectKite: vi.fn(),
  },
}))

describe('EquityUploadPanel & SwitchEquityStatementButton', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState({ userId: 'test-user-123', equitySessionId: null })
    vi.mocked(apiClient.getEquityHistory).mockResolvedValue({
      history: [
        {
          session_id: 'eq-sess-1',
          created_at: '2026-08-01T12:00:00Z',
          num_funds: 5,
          total_value: 250000,
          statement_period: 'kite-sync',
        },
      ],
    } as any)
  })

  it('renders upload panel with Zerodha tab and CSV tab', async () => {
    renderWithProviders(<EquityUploadPanel />)

    expect(await screen.findByText('Connect or Restore Portfolio')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Connect Zerodha API' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'CSV / XLSX Upload' })).toBeInTheDocument()

    // Test Zerodha connect button
    vi.mocked(apiClient.getKiteLoginUrl).mockResolvedValue({
      login_url: 'https://kite.zerodha.com/connect/login',
      state: 'oauth-state-123',
    } as any)

    const connectZerodhaBtn = screen.getByRole('button', { name: /Login with Kite/i })
    await userEvent.click(connectZerodhaBtn)
    expect(apiClient.getKiteLoginUrl).toHaveBeenCalled()
  })

  it('switches to CSV / XLSX Upload tab and uploads files', async () => {
    const { container } = renderWithProviders(<EquityUploadPanel />)

    const csvTab = await screen.findByRole('tab', { name: 'CSV / XLSX Upload' })
    await userEvent.click(csvTab)

    expect(screen.getByText('Upload Holdings File')).toBeInTheDocument()
    expect(screen.getByText('Upload Tradebook File')).toBeInTheDocument()

    const fileInputs = container.querySelectorAll('input[type="file"]')
    const holdingsInput = fileInputs[0] as HTMLInputElement
    const testFile = new File(['symbol,qty\nINFY,10'], 'holdings.csv', { type: 'text/csv' })

    await userEvent.upload(holdingsInput, testFile)

    vi.mocked(apiClient.parseEquityCsv).mockResolvedValue({
      session_id: 'new-eq-sess',
      total_portfolio_value: 150000,
    } as any)

    const parseBtn = screen.getByRole('button', { name: /Analyze Portfolio/i })
    await userEvent.click(parseBtn)

    expect(apiClient.parseEquityCsv).toHaveBeenCalledWith(testFile, undefined)
  })

  it('renders SwitchEquityStatementButton and shows history sessions', async () => {
    renderWithProviders(<SwitchEquityStatementButton sessionId="eq-sess-1" />)

    const switchBtn = screen.getByRole('button', { name: /Switch Portfolio/i })
    expect(switchBtn).toBeInTheDocument()
    await userEvent.click(switchBtn)

    expect(await screen.findByText('Equity Portfolios')).toBeInTheDocument()
    expect(screen.getByText(/5 Stocks/i)).toBeInTheDocument()
  })
})
