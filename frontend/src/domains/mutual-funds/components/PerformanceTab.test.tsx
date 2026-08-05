import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/utils'
import PerformanceTab from './PerformanceTab'
import { apiClient } from '../../../shared/api/client'
import { useAppStore } from '../../../shared/store/appStore'

vi.mock('../../../shared/api/client', () => ({
  apiClient: {
    getPerformance: vi.fn(),
    getCategoryPeers: vi.fn(),
  },
}))

describe('PerformanceTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState({ mfSessionId: 'sid-perf', activeModule: 'mutual_funds' })
    vi.mocked(apiClient.getPerformance).mockResolvedValue({
      portfolio_return: 22.5,
      benchmark_return: 14.2,
      alpha: 8.3,
      portfolio_score: 8.5,
      n_strong: 3,
      n_average: 1,
      n_weak: 0,
      benchmark_label: 'Nifty 50',
      funds: [
        {
          fund: 'Nippon India Growth Fund',
          category: 'Equity',
          cap_type: 'Mid Cap',
          fund_xi: 28.4,
          bench_xi: 18.2,
          alpha: 10.2,
          sharpe: 1.45,
          consistency: 9,
          vol: 12.4,
          status: 'Strong',
          weight: 35.0,
          current_val: 450000,
          gain_val: 120000,
          gain_pct: 36.3,
        },
      ],
    } as any)
    vi.mocked(apiClient.getCategoryPeers).mockResolvedValue({
      peers: [
        { name: 'Kotak Emerging Equity Fund', ret1y: 29.5, ret3y: 24.1, ret5y: 20.2, sharpe: 1.5, expense: 0.7 },
        { name: 'HDFC Mid-Cap Opportunities', ret1y: 27.8, ret3y: 22.4, ret5y: 19.8, sharpe: 1.3, expense: 0.8 },
      ],
      fallback_triggered: false,
    } as any)
  })

  it('renders section header, KPI cards, and fund performance cards', async () => {
    renderWithProviders(<PerformanceTab />)

    expect(screen.getByRole('heading', { name: 'Performance' })).toBeInTheDocument()
    expect(await screen.findByText('+22.50%')).toBeInTheDocument()
    expect(screen.getByText('Your Returns (XIRR)')).toBeInTheDocument()
    expect(screen.getByText('Nifty 50 Returns')).toBeInTheDocument()
    expect(screen.getByText('+14.20%')).toBeInTheDocument()
    expect(screen.getByText('Simple Alpha')).toBeInTheDocument()
    expect(screen.getByText('+8.30%')).toBeInTheDocument()
    expect(screen.getByText('8.5/10')).toBeInTheDocument()

    expect(screen.getByText('Nippon India Growth Fund')).toBeInTheDocument()

    // Expand fund card to see details/peers
    const fundCard = screen.getByText('Nippon India Growth Fund')
    await userEvent.click(fundCard)
    expect(await screen.findByText(/RISK & DEVIATION AUDIT/i)).toBeInTheDocument()
  })

  it('renders error state on API failure', async () => {
    vi.mocked(apiClient.getPerformance).mockRejectedValue(new Error('Network error'))
    renderWithProviders(<PerformanceTab />)

    expect(await screen.findByText('Performance Audit Failed')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Retry Audit/i })).toBeInTheDocument()
  })
})
