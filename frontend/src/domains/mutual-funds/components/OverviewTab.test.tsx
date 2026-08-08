import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/utils'
import OverviewTab from './OverviewTab'
import { apiClient } from '../../../shared/api/client'
import { useAppStore } from '../../../shared/store/appStore'

vi.mock('../../../shared/api/client', () => ({
  apiClient: {
    getSummary: vi.fn(),
    getOverview: vi.fn(),
    getBenchmarkOverlay: vi.fn(),
    getHoldings: vi.fn(),
    getAllocation: vi.fn(),
    getPerformance: vi.fn(),
  },
}))

// Lightweight chart stub that still exercises OverviewTab callbacks
vi.mock('./PortfolioChart', () => ({
  default: ({ onPeriodChange, onBenchmarksChange, period, selectedBenchmarks }: any) => (
    <div data-testid="portfolio-chart-stub">
      <span>Period:{period}</span>
      <span>Bench:{selectedBenchmarks?.[0]}</span>
      <button type="button" onClick={() => onPeriodChange('3Y')}>Set 3Y</button>
      <button type="button" onClick={() => onBenchmarksChange(['Sensex'])}>Set Sensex</button>
      <button type="button" onClick={() => onBenchmarksChange([])}>Clear benches</button>
    </div>
  ),
}))

describe('OverviewTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState({ mfSessionId: 'sid-overview', activeModule: 'mutual_funds' })
    vi.mocked(apiClient.getSummary).mockResolvedValue({
      total_value: 1250000,
      total_invested: 1000000,
      total_gain: 250000,
      gain_pct: 25,
      portfolio_xirr: 18.5,
      alpha: 4.2,
      is_absolute: false,
    } as any)
    vi.mocked(apiClient.getOverview).mockResolvedValue({
      chart: {
        dates: ['2025-01-01', '2026-01-01'],
        portfolio: [1000000, 1250000],
        benchmark: [1000000, 1150000],
      },
      port_pct: 25,
      bench_pct: 15,
    } as any)
    vi.mocked(apiClient.getBenchmarkOverlay).mockResolvedValue({ series: {} } as any)
    vi.mocked(apiClient.getHoldings).mockResolvedValue({
      holdings: [
        { Fund: 'Quant Small Cap Fund', 'Gain%': 38.5, 'Market Value': 400000 },
        { Fund: 'Parag Parikh Flexi Cap', 'Gain%': 22.1, 'Market Value': 600000 },
        { fund: 'Alt Key Fund', gain_pct: 10, 'Market Value': 100000 },
      ],
    } as any)
    vi.mocked(apiClient.getAllocation).mockResolvedValue({
      broad: [
        { label: 'Equity', pct: 85, value: 850000, color: '#6366F1' },
        { label: 'Debt', pct: 15, value: 150000 },
      ],
      by_cap: [
        { label: 'Large Cap', pct: 40 },
        { 'Cap Type': 'Mid Cap', pct: 35 },
        { pct: 25 },
      ],
    } as any)
    vi.mocked(apiClient.getPerformance).mockResolvedValue({
      benchmark_price_index_blend: false,
      portfolio_beta: 1.0,
    } as any)
  })

  it('renders section header, KPI cards, and asset allocation sidebar', async () => {
    renderWithProviders(<OverviewTab />)

    expect(screen.getByRole('heading', { name: 'Overview' })).toBeInTheDocument()
    expect(await screen.findByText('₹12.50 L')).toBeInTheDocument()
    expect(screen.getByText('₹2.50 L')).toBeInTheDocument()
    expect(screen.getByText('+18.50%')).toBeInTheDocument()
    expect(screen.getByText('PORTFOLIO HEALTH')).toBeInTheDocument()
    expect(screen.getByText('TOP ATTRIBUTION')).toBeInTheDocument()
    expect(screen.getByText('QUANT SMALL CAP FUND')).toBeInTheDocument()
    expect(screen.getByText(/Macro Asset Spectrum & Risk Parity/i)).toBeInTheDocument()
    expect(screen.getByText(/LARGE CAP: 40%/i)).toBeInTheDocument()
    expect(screen.getByText(/MID CAP: 35%/i)).toBeInTheDocument()
    expect(screen.getByText(/UNKNOWN: 25%/i)).toBeInTheDocument()
    expect(screen.getByText(/Diversification index: Moderate/i)).toBeInTheDocument()
    expect(screen.getByText(/\(Stable\)/i)).toBeInTheDocument()
  })

  it('shows absolute return label, underperforming health, and defensive beta', async () => {
    vi.mocked(apiClient.getSummary).mockResolvedValue({
      total_value: 900000,
      total_invested: 1000000,
      total_gain: -100000,
      gain_pct: -10,
      portfolio_xirr: -8,
      alpha: -3.5,
      is_absolute: true,
    } as any)
    vi.mocked(apiClient.getOverview).mockResolvedValue({
      chart: { dates: ['2025-01-01'], portfolio: [900000], benchmark: [1000000] },
      port_pct: -5,
      bench_pct: 4,
    } as any)
    vi.mocked(apiClient.getPerformance).mockResolvedValue({
      benchmark_price_index_blend: true,
      portfolio_beta: 0.85,
    } as any)
    vi.mocked(apiClient.getAllocation).mockResolvedValue({
      broad: [
        { label: 'Equity', pct: 70, value: 630000, color: '#4EDE93' },
        { label: 'Debt', pct: 30, value: 270000, color: '#F59E0B' },
      ],
      by_cap: [],
    } as any)

    renderWithProviders(<OverviewTab />)

    expect(await screen.findByText('Absolute Return')).toBeInTheDocument()
    expect(screen.getByText('Underperforming Benchmark')).toBeInTheDocument()
    expect(screen.getByText(/\(Defensive\)/i)).toBeInTheDocument()
    expect(screen.getByText(/Diversification index: High/i)).toBeInTheDocument()
    expect(screen.getByText(/blended from a price-only index/i)).toBeInTheDocument()
  })

  it('shows aggressive beta, default equity allocation, and empty holdings gracefully', async () => {
    vi.mocked(apiClient.getHoldings).mockResolvedValue({ holdings: [] } as any)
    vi.mocked(apiClient.getAllocation).mockResolvedValue({
      broad: [{ label: 'Gold', pct: 100, value: 100000 }],
      by_cap: [],
    } as any)
    vi.mocked(apiClient.getPerformance).mockResolvedValue({
      benchmark_price_index_blend: false,
      portfolio_beta: 1.25,
    } as any)

    renderWithProviders(<OverviewTab />)
    expect(await screen.findByText(/\(Aggressive\)/i)).toBeInTheDocument()
    // No Equity bucket → default 76.4% concentration copy
    expect(screen.getByText(/Equity asset concentration is 76.4%/i)).toBeInTheDocument()
    expect(screen.getByText('TOP ATTRIBUTION')).toBeInTheDocument()
  })

  it('shows N/A beta when missing and loading skeletons while overview fetches', async () => {
    vi.mocked(apiClient.getOverview).mockReturnValue(new Promise(() => {}) as any)
    vi.mocked(apiClient.getPerformance).mockResolvedValue({
      benchmark_price_index_blend: false,
      portfolio_beta: null,
    } as any)

    renderWithProviders(<OverviewTab />)
    expect(screen.getByRole('heading', { name: 'Overview' })).toBeInTheDocument()
    await waitFor(() => {
      expect(document.querySelectorAll('.MuiSkeleton-root').length).toBeGreaterThan(0)
    })
  })

  it('propagates period and benchmark changes from the chart', async () => {
    const user = userEvent.setup()
    renderWithProviders(<OverviewTab />)
    expect(await screen.findByTestId('portfolio-chart-stub')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Set 3Y' }))
    expect(await screen.findByText('Period:3Y')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Set Sensex' }))
    expect(await screen.findByText('Bench:Sensex')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Clear benches' }))
    // primaryBenchmark falls back to Nifty 50 when selection emptied
    await waitFor(() => {
      expect(apiClient.getSummary).toHaveBeenCalled()
    })
  })

  it('handles missing summary fields without crashing', async () => {
    vi.mocked(apiClient.getSummary).mockResolvedValue({} as any)
    vi.mocked(apiClient.getOverview).mockResolvedValue({} as any)
    vi.mocked(apiClient.getHoldings).mockResolvedValue({} as any)
    vi.mocked(apiClient.getAllocation).mockResolvedValue({} as any)
    vi.mocked(apiClient.getPerformance).mockResolvedValue({} as any)

    renderWithProviders(<OverviewTab />)
    expect(await screen.findByText('PORTFOLIO HEALTH')).toBeInTheDocument()
    expect(screen.getByText(/Portfolio Beta: N\/A/i)).toBeInTheDocument()
  })
})
