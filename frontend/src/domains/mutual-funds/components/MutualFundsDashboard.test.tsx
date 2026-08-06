import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../../../test/utils'
import MutualFundsDashboard from './MutualFundsDashboard'
import { useAppStore } from '../../../shared/store/appStore'
import { apiClient } from '../../../shared/api/client'

vi.mock('../../../shared/api/client', () => ({
  apiClient: {
    getSummary: vi.fn().mockResolvedValue({ total_value: 1000000, total_invested: 800000, total_gain: 200000, gain_pct: 25 }),
    getOverview: vi.fn().mockResolvedValue({ chart: { dates: ['2026-01-01'], portfolio: [100000], benchmark: [100000] }, port_pct: 12, bench_pct: 10 }),
    getBenchmarkOverlay: vi.fn().mockResolvedValue({ series: {} }),
    getHoldings: vi.fn().mockResolvedValue({ holdings: [] }),
    getAllocation: vi.fn().mockResolvedValue({ broad: [{ label: 'Equity', pct: 80 }] }),
    getPerformance: vi.fn().mockResolvedValue({ benchmark_price_index_blend: false }),
    getUploadHistory: vi.fn().mockResolvedValue([]),
  },
}))

describe('MutualFundsDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders MFUploadPanel when no session is active', () => {
    useAppStore.setState({ mfSessionId: null, activeModule: 'mutual_funds' })
    renderWithProviders(<MutualFundsDashboard />)

    expect(screen.getByText(/Upload CAS PDF/i)).toBeInTheDocument()
  })

  it('renders tabs navigation when session is active', async () => {
    useAppStore.setState({ mfSessionId: 'sid-mf-123', activeModule: 'mutual_funds' })
    renderWithProviders(<MutualFundsDashboard />, { initialEntries: ['/mutual-funds/overview'] })

    expect(screen.getByText('MUTUAL FUNDS')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Overview' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Holdings' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Performance' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Compare' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Wealth Journey' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Insights & Rebalance' })).toBeInTheDocument()
  })
})
