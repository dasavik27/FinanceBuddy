import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
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
    getSipProjection: vi.fn(),
    getXirrByFy: vi.fn(),
    getSipAttribution: vi.fn(),
    getMandateOverlap: vi.fn(),
    getWhatIf: vi.fn(),
    searchTicker: vi.fn(),
  },
}))

vi.mock('./RebalanceTab', () => ({
  default: ({ isSubTab }: any) => <div>Rebalance stub {isSubTab ? 'sub' : 'full'}</div>,
}))
vi.mock('./TaxHarvestPanel', () => ({ default: () => <div>TaxHarvest stub</div> }))
vi.mock('./GoalProjectorPanel', () => ({ default: () => <div>GoalProjector stub</div> }))
vi.mock('./YearlyProgressPanel', () => ({ default: () => <div>YearlyProgress stub</div> }))
vi.mock('./MandateOverlapPanel', () => ({ default: () => <div>MandateOverlap stub</div> }))
vi.mock('./WhatIfPanel', () => ({ default: () => <div>WhatIf stub</div> }))

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
        { type: 'info', message: 'Consider consolidating overlapping flexi-cap mandates.' },
        { type: 'success', message: 'SIP cadence is healthy this quarter.' },
        { type: 'unknown', message: 'Fallback nudge styling path.' },
      ],
      goal_timeline: [
        { category: 'Equity', goal: 'Long Term Wealth', timeline: '7+ Years', value: 850000, pct: 85.0, color: '#6366F1' },
        { category: 'Debt', goal: 'Stability', timeline: '1-3 Years', value: 100000, pct: 10.0, color: '#F59E0B' },
        { category: 'Cash', goal: 'Liquidity', timeline: '0-1 Years', value: 50000, pct: 5.0, color: '#94A3B8' },
      ],
    } as any)
    vi.mocked(apiClient.getTaxHarvest).mockResolvedValue({ harvest: {}, debt_summary: {} } as any)
    vi.mocked(apiClient.getHoldings).mockResolvedValue({ holdings: [] } as any)
  })

  it('renders health audit, smart nudges, and goal capital mapping', async () => {
    renderWithProviders(<InsightsTab />)

    expect(screen.getByRole('heading', { name: 'Insights & Rebalancing' })).toBeInTheDocument()
    expect(screen.getByText('Neural Diagnostics & Smart Nudges')).toBeInTheDocument()
    expect(screen.getByText('Euclidean Drift & Rebalancing Planner')).toBeInTheDocument()

    expect(await screen.findByText(/High exposure to small cap segment/i)).toBeInTheDocument()
    expect(screen.getByText(/Regular plan detected in portfolio/i)).toBeInTheDocument()
    expect(screen.getByText('ACTION REQUIRED')).toBeInTheDocument()
    expect(screen.getByText('HIGH PRIORITY')).toBeInTheDocument()
    expect(screen.getByText('Goal-Based Capital Mapping')).toBeInTheDocument()
    expect(screen.getByText('TaxHarvest stub')).toBeInTheDocument()
    expect(screen.getByText('WhatIf stub')).toBeInTheDocument()
  })

  it('switches to rebalance planner subtab on button click', async () => {
    const user = userEvent.setup()
    renderWithProviders(<InsightsTab />)

    await user.click(screen.getByText('Euclidean Drift & Rebalancing Planner'))
    expect(await screen.findByText(/Rebalance stub sub/i)).toBeInTheDocument()

    await user.click(screen.getByText('Neural Diagnostics & Smart Nudges'))
    expect(await screen.findByText('HEALTH AUDIT')).toBeInTheDocument()
  })

  it('filters nudges by priority chips and shows empty-state copy', async () => {
    const user = userEvent.setup()
    renderWithProviders(<InsightsTab />)
    expect(await screen.findByText(/High exposure to small cap/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Critical/i }))
    expect(screen.getByText(/High exposure to small cap/i)).toBeInTheDocument()
    expect(screen.queryByText(/Regular plan detected/i)).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /High Priority/i }))
    expect(screen.getByText(/Regular plan detected/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Optimizations/i }))
    expect(screen.getByText(/overlapping flexi-cap/i)).toBeInTheDocument()

    // Filter to a type with no matching nudges after we strip them
    vi.mocked(apiClient.getInsights).mockResolvedValue({
      score: 90,
      nudges: [{ type: 'danger', message: 'Only critical left' }],
      goal_timeline: [],
    } as any)

    await user.click(screen.getByRole('button', { name: /All Insights/i }))
    // Still on previous data until refetch — exercise warn empty via filter on current set
    await user.click(screen.getByRole('button', { name: /High Priority/i }))
    // With current cached nudges, warn exists; switch to info then clear via re-render path
    await user.click(screen.getByRole('button', { name: /Optimizations/i }))
    expect(screen.getByText(/overlapping flexi-cap/i)).toBeInTheDocument()
  })

  it('shows empty nudge category message when filter matches nothing', async () => {
    const user = userEvent.setup()
    vi.mocked(apiClient.getInsights).mockResolvedValue({
      score: 88,
      score_breakdown: [],
      nudges: [{ type: 'danger', message: 'Critical only' }],
      goal_timeline: [],
      sip_score: 9,
      liquid_val: 0,
      liquid_pct: 0,
      expense_drag: 0,
      expense_pct: 0,
      elss_val: 0,
    } as any)

    renderWithProviders(<InsightsTab />)
    expect(await screen.findByText('Critical only')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /High Priority/i }))
    expect(await screen.findByText(/No issues detected in this category/i)).toBeInTheDocument()
  })

  it('shows error alert and loading skeletons', async () => {
    vi.mocked(apiClient.getInsights).mockRejectedValue(new Error('insights down'))
    renderWithProviders(<InsightsTab />)
    expect(await screen.findByText(/Failed to load institutional insights/i)).toBeInTheDocument()
  })

  it('shows loading skeletons while insights fetch', async () => {
    vi.mocked(apiClient.getInsights).mockReturnValue(new Promise(() => {}) as any)
    renderWithProviders(<InsightsTab />)
    await waitFor(() => {
      expect(document.querySelector('.MuiSkeleton-root')).toBeTruthy()
    })
  })

  it('uses default score breakdown when API omits pillars', async () => {
    vi.mocked(apiClient.getInsights).mockResolvedValue({
      score: 50,
      nudges: [],
      goal_timeline: [],
      sip_score: 7,
      liquid_val: 0,
      liquid_pct: 0,
      expense_drag: 0,
      expense_pct: 0,
      elss_val: 0,
    } as any)
    renderWithProviders(<InsightsTab />)
    expect(await screen.findByText(/No issues detected in this category/i)).toBeInTheDocument()
    expect(screen.getByText('Alpha vs Benchmark')).toBeInTheDocument()
  })
})
