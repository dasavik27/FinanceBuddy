import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/utils'
import InsightsTab from './InsightsTab'
import { apiClient } from '../../../shared/api/client'
import { useAppStore } from '../../../shared/store/appStore'

vi.mock('../../../shared/api/client', () => ({
  apiClient: {
    getInsights: vi.fn(),
    getRebalancePlan: vi.fn(),
    getTaxHarvest: vi.fn(),
    getGoalTimeline: vi.fn(),
    getWhatIfScenario: vi.fn(),
    getHoldings: vi.fn(),
  },
}))

describe('InsightsTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState({ mfSessionId: 'sid-insights', activeModule: 'mutual_funds' })
    vi.mocked(apiClient.getInsights).mockResolvedValue({
      score: 82,
      score_breakdown: [
        { label: 'Alpha vs Benchmark', max: 30, score: 25 },
        { label: 'Fund Diversification', max: 25, score: 20 },
      ],
      sip_score: 8.5,
      liquid_val: 150000,
      liquid_pct: 15.0,
      expense_drag: 12000,
      expense_pct: 0.85,
      elss_val: 150000,
      nudges: [
        { type: 'danger', message: 'High exposure to small cap segment exceeds recommended limit.' },
        { type: 'warn', message: 'Regular plan detected in portfolio with high TER.' },
      ],
      goal_timeline: [
        { category: 'Equity', goal: 'Long Term Wealth', timeline: '7+ Years', value: 850000, pct: 85.0, color: '#6366F1' },
      ],
    } as any)
    vi.mocked(apiClient.getTaxHarvest).mockResolvedValue({
      ltcg_gain: 75000,
      stcg_gain: 15000,
      harvestable_gain: 50000,
      estimated_tax_savings: 5000,
      opportunities: [],
    } as any)
    vi.mocked(apiClient.getHoldings).mockResolvedValue({
      holdings: [],
    } as any)
  })

  it('renders health audit, smart nudges, and goal capital mapping', async () => {
    renderWithProviders(<InsightsTab />)

    expect(screen.getByRole('heading', { name: 'Insights & Rebalancing' })).toBeInTheDocument()
    expect(screen.getByText('Neural Diagnostics & Smart Nudges')).toBeInTheDocument()
    expect(screen.getByText('Euclidean Drift & Rebalancing Planner')).toBeInTheDocument()

    expect(await screen.findByText(/High exposure to small cap segment/i)).toBeInTheDocument()
    expect(screen.getByText(/Regular plan detected in portfolio/i)).toBeInTheDocument()
  })

  it('switches to rebalance planner subtab on button click', async () => {
    vi.mocked(apiClient.getRebalancePlan).mockResolvedValue({
      drift_score: 18.5,
      actions: [],
    } as any)

    renderWithProviders(<InsightsTab />)

    const rebalanceBtn = screen.getByText('Euclidean Drift & Rebalancing Planner')
    await userEvent.click(rebalanceBtn)

    expect(await screen.findByText(/Euclidean Drift/i)).toBeInTheDocument()
  })
})
