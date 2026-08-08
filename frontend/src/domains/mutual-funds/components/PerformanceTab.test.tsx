import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
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

const midCapFund = {
  fund: 'Nippon India Growth Fund Direct Growth Extremely Long Name Truncation',
  category: 'Equity',
  cap_type: 'Mid Cap',
  fund_xi: 28.4,
  bench_xi: 18.2,
  bench_display: 'Nifty Midcap 150',
  alpha: 10.2,
  sharpe: 1.45,
  sortino: 1.9,
  consistency: 9,
  vol: 12.4,
  tracking_error: 3.2,
  beta: 1.1,
  max_dd: -22.5,
  er: 0.75,
  up_capture: 110,
  down_capture: 85,
  info_ratio: 0.8,
  calmar: 1.2,
  treynor: 0.9,
  pe_ratio: 28.5,
  pb_ratio: 4.2,
  action: 'Hold',
  verdict: 'Strong',
  verdict_reason: 'Consistent alpha',
  fund_score: 9,
  cur_value: 450000,
  color: '#6366F1',
  fund_rolls: [null, null, null, 29.5, 24.0, 20.1],
  ret_3y: 24.0,
}

const debtFund = {
  fund: 'HDFC Short Term Debt Fund',
  category: 'Debt',
  cap_type: 'Debt',
  fund_xi: 7.2,
  bench_xi: 6.5,
  alpha: 0.7,
  sharpe: 0.9,
  consistency: 6,
  vol: 2.1,
  is_debt: true,
  ytm_proxy: 7.8,
  modified_duration: 2.5,
  action: 'Review',
  verdict: 'Average',
  cur_value: 120000,
}

const smallCapFund = {
  fund: 'Quant Small Cap',
  category: 'Equity',
  cap_type: 'Small Cap',
  fund_xi: -3.5,
  bench_xi: 5.0,
  alpha: -8.5,
  sharpe: null,
  sortino: null,
  consistency: 3,
  vol: 28,
  is_absolute: true,
  ret_3y: null,
  verdict: 'Weak',
  action: 'Monitor',
}

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
      funds: [midCapFund, debtFund, smallCapFund],
    } as any)
    vi.mocked(apiClient.getCategoryPeers).mockResolvedValue({
      peers: [
        { name: 'Kotak Emerging Equity Fund', ret1y: 29.5, ret3y: 24.1, ret5y: 20.2, sharpe: 1.5, expense: 0.7 },
        { name: 'HDFC Mid-Cap Opportunities', ret1y: 27.8, ret3y: 22.4, ret5y: 19.8, sharpe: 1.3, expense: 0.8 },
        { name: 'Axis Midcap Fund', ret1y: 18.0, ret3y: 15.0, ret5y: 14.0, sharpe: 1.0, expense: 0.9 },
      ],
      fallback_triggered: false,
    } as any)
  })

  it('renders section header, KPI cards, and fund performance cards', async () => {
    const user = userEvent.setup()
    renderWithProviders(<PerformanceTab />)

    expect(screen.getByRole('heading', { name: 'Performance' })).toBeInTheDocument()
    expect(await screen.findByText('+22.50%')).toBeInTheDocument()
    expect(screen.getByText('Your Returns (XIRR)')).toBeInTheDocument()
    expect(screen.getByText('Nifty 50 Returns')).toBeInTheDocument()
    expect(screen.getByText('+14.20%')).toBeInTheDocument()
    expect(screen.getByText('Simple Alpha')).toBeInTheDocument()
    expect(screen.getByText('+8.30%')).toBeInTheDocument()
    expect(screen.getByText('8.5/10')).toBeInTheDocument()

    expect(screen.getByText(/Nippon India Growth Fund/i)).toBeInTheDocument()

    const fundCard = screen.getByText(/Nippon India Growth Fund/i)
    await user.click(fundCard)
    expect(await screen.findByText(/RISK & DEVIATION AUDIT/i)).toBeInTheDocument()
    expect(screen.getByText(/CAPTURE & EFFICIENCY DYNAMICS/i)).toBeInTheDocument()
    expect(screen.getByText(/VALUATION & RADAR PROFILE/i)).toBeInTheDocument()
    expect(screen.getByText(/ACTION: HOLD/i)).toBeInTheDocument()
    expect(screen.getByText(/EST\. P\/E RATIO/i)).toBeInTheDocument()

    // Peer strip loads after expand
    expect(await screen.findByText(/CATEGORY PEERS/i)).toBeInTheDocument()
    expect(screen.getByText(/Kotak Emerging Equity Fund/i)).toBeInTheDocument()

    // Sort peers by 3Y / 5Y / Sharpe
    await user.click(screen.getByRole('button', { name: '3Y' }))
    await user.click(screen.getByRole('button', { name: '5Y' }))
    await user.click(screen.getByRole('button', { name: 'SHARPE' }))
    await user.click(screen.getByRole('button', { name: '1Y' }))
  }, 60000)

  it('filters by category chips and sorts by attribution options', async () => {
    const user = userEvent.setup()
    renderWithProviders(<PerformanceTab />)
    expect(await screen.findByText(/Nippon India Growth Fund/i)).toBeInTheDocument()

    // Filter chips live in CATEGORY SPECTRUM (also appear as CategoryBadge labels)
    const spectrum = screen.getByText('CATEGORY SPECTRUM').closest('.MuiGrid-item') as HTMLElement
    await user.click(within(spectrum).getByText('Mid Cap'))
    expect(screen.getByText(/Nippon India Growth Fund/i)).toBeInTheDocument()
    expect(screen.queryByText('Quant Small Cap')).not.toBeInTheDocument()

    await user.click(within(spectrum).getByText('Debt'))
    expect(await screen.findByText('HDFC Short Term Debt Fund')).toBeInTheDocument()

    await user.click(within(spectrum).getByText('All'))
    expect(screen.getByText('Quant Small Cap')).toBeInTheDocument()

    // Open sort select and exercise each option
    const sortSelect = screen.getByRole('combobox')
    const sortOptions = [
      'XIRR Return (High to Low)',
      'Sharpe Ratio (Risk-Adjusted)',
      'Consistency Score (High to Low)',
      'Volatility (Low to High)',
      'Alpha Generated (High to Low)',
    ]
    for (const label of sortOptions) {
      await user.click(sortSelect)
      const option = await screen.findByRole('option', { name: label })
      await user.click(option)
    }
  }, 60000)

  it('expands debt fund valuation panel and absolute-return badge', async () => {
    const user = userEvent.setup()
    renderWithProviders(<PerformanceTab />)
    expect(await screen.findByText('HDFC Short Term Debt Fund')).toBeInTheDocument()

    await user.click(screen.getByText('HDFC Short Term Debt Fund'))
    expect(await screen.findByText(/YIELD \(YTM\)/i)).toBeInTheDocument()
    expect(screen.getByText('7.8%')).toBeInTheDocument()
    expect(screen.getByText('2.5Y')).toBeInTheDocument()
    expect(screen.getByText(/ACTION: REVIEW/i)).toBeInTheDocument()

    await user.click(screen.getByText('Quant Small Cap'))
    expect(await screen.findByText('ABS')).toBeInTheDocument()
  })

  it('covers absolute / negative portfolio hero copy and peer fallback banner', async () => {
    const user = userEvent.setup()
    vi.mocked(apiClient.getPerformance).mockResolvedValue({
      portfolio_return: -4.2,
      benchmark_return: 2.1,
      alpha: -6.3,
      portfolio_score: 4,
      n_strong: 0,
      n_average: 1,
      n_weak: 2,
      is_absolute: true,
      benchmark_label: 'Nifty 50',
      funds: [midCapFund],
    } as any)
    vi.mocked(apiClient.getCategoryPeers).mockResolvedValue({
      peers: [
        { name: 'Peer A', ret1y: 40, ret3y: 30, ret5y: 25, sharpe: 2, expense: 0.5 },
      ],
      fallback_triggered: true,
    } as any)

    renderWithProviders(<PerformanceTab />)
    expect(await screen.findByText('Your Returns (Absolute)')).toBeInTheDocument()
    expect(screen.getByText(/currently in negative territory/i)).toBeInTheDocument()
    expect(screen.getByText(/index fund may serve you better/i)).toBeInTheDocument()

    await user.click(screen.getByText(/Nippon India Growth Fund/i))
    expect(await screen.findByText(/CATEGORY DEGRADATION ACTIVE/i)).toBeInTheDocument()
  })

  it('renders error state on API failure and retries', async () => {
    const user = userEvent.setup()
    vi.mocked(apiClient.getPerformance).mockRejectedValue(new Error('Network error'))
    renderWithProviders(<PerformanceTab />)

    expect(await screen.findByText('Performance Audit Failed')).toBeInTheDocument()
    const retry = screen.getByRole('button', { name: /Retry Audit/i })
    vi.mocked(apiClient.getPerformance).mockResolvedValue({
      portfolio_return: 10,
      benchmark_return: 8,
      alpha: 2,
      portfolio_score: 7,
      n_strong: 1,
      n_average: 0,
      n_weak: 0,
      funds: [midCapFund],
    } as any)
    await user.click(retry)
    await waitFor(() => expect(apiClient.getPerformance).toHaveBeenCalled())
  })

  it('handles empty peers and peer load errors gracefully', async () => {
    const user = userEvent.setup()
    vi.mocked(apiClient.getCategoryPeers).mockRejectedValue(new Error('peers down'))
    renderWithProviders(<PerformanceTab />)
    expect(await screen.findByText(/Nippon India Growth Fund/i)).toBeInTheDocument()
    await user.click(screen.getByText(/Nippon India Growth Fund/i))
    expect(await screen.findByText(/RISK & DEVIATION AUDIT/i)).toBeInTheDocument()
    // No CATEGORY PEERS section when peers fail / empty
    await waitFor(() => {
      expect(screen.queryByText(/CATEGORY PEERS —/i)).not.toBeInTheDocument()
    })
  })

  it('covers marginal alpha, warn health score, and outperformance copy', async () => {
    vi.mocked(apiClient.getPerformance).mockResolvedValue({
      portfolio_return: 12,
      benchmark_return: 10,
      alpha: 1.2,
      portfolio_score: 6,
      n_strong: 1,
      n_average: 2,
      n_weak: 1,
      benchmark_label: 'Nifty Midcap 150',
      funds: [midCapFund],
    } as any)

    renderWithProviders(<PerformanceTab />)
    expect(await screen.findByText(/marginally ahead of the market/i)).toBeInTheDocument()
    expect(screen.getByText(/You outperformed Nifty Midcap 150/i)).toBeInTheDocument()
    expect(screen.getByText('6/10')).toBeInTheDocument()
  })

  it('covers excellent alpha and benchmark-ahead hero copy', async () => {
    vi.mocked(apiClient.getPerformance).mockResolvedValue({
      portfolio_return: 8,
      benchmark_return: 14,
      alpha: 3.5,
      portfolio_score: 7.5,
      n_strong: 2,
      n_average: 0,
      n_weak: 0,
      funds: [midCapFund],
    } as any)

    renderWithProviders(<PerformanceTab />)
    expect(await screen.findByText(/Excellent — your fund picks are adding real value/i)).toBeInTheDocument()
    expect(screen.getByText(/Nifty 50 would have done better/i)).toBeInTheDocument()
  })

  it('expands sparse / unknown / monitor funds and filters remaining categories', async () => {
    const user = userEvent.setup()
    const sparseFund = {
      name: 'Mystery Sparse Fund',
      category: 'Equity',
      cap_type: 'Equity',
      fund_xi: -1.2,
      bench_xi: 2,
      alpha: -3.2,
      sharpe: null,
      sortino: null,
      consistency: 4,
      vol: null,
      tracking_error: null,
      beta: null,
      max_dd: null,
      er: null,
      up_capture: 90,
      down_capture: 110,
      info_ratio: 0.2,
      calmar: null,
      treynor: null,
      pe_ratio: null,
      pb_ratio: null,
      action: 'Monitor',
      verdict: 'Average',
      ret_3y: -4.5,
      fund_rolls: [null, null, null, null, null, null],
      color: '#F59E0B',
    }
    const elssFund = {
      fund: 'Axis Long Term Equity ELSS',
      category: 'ELSS',
      cap_type: 'ELSS',
      fund_xi: 15,
      alpha: 1,
      sharpe: 1.1,
      consistency: 7,
      verdict: 'Strong',
      action: 'Hold',
      cur_value: 90000,
    }
    const flexiFund = {
      fund: 'Parag Parikh Flexi Cap Fund',
      category: 'Flexi Cap',
      cap_type: 'Flexi/Multi Cap',
      fund_xi: 18,
      alpha: 2,
      sharpe: 1.2,
      consistency: 8,
      verdict: 'Strong',
      action: 'Hold',
    }
    const largeFund = {
      fund: 'HDFC Top 100',
      category: 'Large Cap',
      cap_type: 'Large Cap',
      fund_xi: 14,
      alpha: 0.5,
      sharpe: 1.0,
      consistency: 7,
      verdict: 'Average',
      action: 'Hold',
    }
    const debtDefaults = {
      fund: 'ICICI Debt Defaults',
      category: 'Debt',
      cap_type: 'Debt',
      fund_xi: 6,
      alpha: 0.2,
      is_debt: true,
      ytm_proxy: null,
      modified_duration: null,
      action: 'Hold',
      verdict: 'Average',
    }

    vi.mocked(apiClient.getPerformance).mockResolvedValue({
      portfolio_return: 10,
      benchmark_return: 9,
      alpha: 1,
      portfolio_score: 6,
      n_strong: 2,
      n_average: 2,
      n_weak: 1,
      funds: [sparseFund, elssFund, flexiFund, largeFund, debtDefaults, smallCapFund],
    } as any)
    vi.mocked(apiClient.getCategoryPeers).mockResolvedValue({
      peers: [
        { name: 'A Peer With Extremely Long Name That Should Truncate In The Peer Table Row', ret1y: null, ret3y: -2, ret5y: null, sharpe: null, expense: null },
        { name: 'Weak Peer', ret1y: -5, ret3y: -3, ret5y: -1, sharpe: 0.2, expense: 1.1 },
        { name: 'Mid Peer', ret1y: 12, ret3y: 10, ret5y: 9, sharpe: 0.9, expense: 0.6 },
      ],
      fallback_triggered: false,
    } as any)

    renderWithProviders(<PerformanceTab />)
    expect(await screen.findByText('Mystery Sparse Fund')).toBeInTheDocument()

    const spectrum = screen.getByText('CATEGORY SPECTRUM').closest('.MuiGrid-item') as HTMLElement
    await user.click(within(spectrum).getByText('ELSS'))
    expect(screen.getByText('Axis Long Term Equity ELSS')).toBeInTheDocument()
    await user.click(within(spectrum).getByText('Flexi/Multi Cap'))
    expect(screen.getByText('Parag Parikh Flexi Cap Fund')).toBeInTheDocument()
    await user.click(within(spectrum).getByText('Large Cap'))
    expect(screen.getByText('HDFC Top 100')).toBeInTheDocument()
    await user.click(within(spectrum).getByText('Small Cap'))
    expect(screen.getByText('Quant Small Cap')).toBeInTheDocument()
    await user.click(within(spectrum).getByText('All'))

    await user.click(screen.getByText('Mystery Sparse Fund'))
    expect(await screen.findByText(/ACTION: MONITOR/i)).toBeInTheDocument()
    expect(screen.getByText(/RISK & DEVIATION AUDIT/i)).toBeInTheDocument()
    // N/A risk metrics + capture colour branches
    expect(screen.getAllByText('N/A').length).toBeGreaterThan(3)
    expect(await screen.findByText(/CATEGORY PEERS/i)).toBeInTheDocument()

    await user.click(screen.getByText('ICICI Debt Defaults'))
    expect(await screen.findByText('7.5%')).toBeInTheDocument()
    expect(screen.getByText('3.0Y')).toBeInTheDocument()
  })
  it('shows peer loading skeletons then empty peers null path', async () => {
    const user = userEvent.setup()
    let resolvePeers: (v: unknown) => void
    vi.mocked(apiClient.getCategoryPeers).mockReturnValue(
      new Promise((resolve) => {
        resolvePeers = resolve
      }) as any,
    )

    renderWithProviders(<PerformanceTab />)
    expect(await screen.findByText(/Nippon India Growth Fund/i)).toBeInTheDocument()
    await user.click(screen.getByText(/Nippon India Growth Fund/i))
    expect(await screen.findByText('CATEGORY PEERS')).toBeInTheDocument()
    expect(document.querySelector('.MuiSkeleton-root')).toBeTruthy()

    resolvePeers!({ peers: [], fallback_triggered: false })
    await waitFor(() => {
      expect(screen.queryByText(/CATEGORY PEERS —/i)).not.toBeInTheDocument()
    })
  })

  it('ranks your fund mid/low among peers and sorts by sharpe', async () => {
    const user = userEvent.setup()
    vi.mocked(apiClient.getCategoryPeers).mockResolvedValue({
      peers: [
        { name: 'Top Peer', ret1y: 50, ret3y: 40, ret5y: 30, sharpe: 2.5, expense: 0.4 },
        { name: 'Second Peer', ret1y: 40, ret3y: 30, ret5y: 25, sharpe: 2.0, expense: 0.5 },
        { name: 'Third Peer', ret1y: 35, ret3y: 28, ret5y: 22, sharpe: 1.8, expense: 0.55 },
        { name: 'Fourth Peer', ret1y: 32, ret3y: 26, ret5y: 21, sharpe: 1.6, expense: 0.6 },
        { name: 'Fifth Peer', ret1y: 31, ret3y: 25, ret5y: 20, sharpe: 1.55, expense: 0.65 },
      ],
      fallback_triggered: false,
    } as any)

    renderWithProviders(<PerformanceTab />)
    await user.click(await screen.findByText(/Nippon India Growth Fund/i))
    expect(await screen.findByText(/Rank \d+ of \d+/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'SHARPE' }))
    expect(screen.getByText(/Top Peer/i)).toBeInTheDocument()
  })

  it('falls back category peers when fund has no cap_type or category', async () => {
    const user = userEvent.setup()
    vi.mocked(apiClient.getPerformance).mockResolvedValue({
      portfolio_return: 10,
      benchmark_return: 9,
      alpha: 1,
      portfolio_score: 6,
      n_strong: 1,
      n_average: 0,
      n_weak: 0,
      funds: [{ fund: 'Bare Fund', fund_xi: 10, alpha: 1, verdict: 'Average' }],
    } as any)
    vi.mocked(apiClient.getCategoryPeers).mockResolvedValue({
      peers: [{ name: 'Default Large Cap Peer', ret1y: 11, ret3y: 10, ret5y: 9, sharpe: 1, expense: 0.7 }],
      fallback_triggered: false,
    } as any)

    renderWithProviders(<PerformanceTab />)
    await user.click(await screen.findByText('Bare Fund'))
    await waitFor(() => {
      expect(apiClient.getCategoryPeers).toHaveBeenCalledWith('Large Cap')
    })
    expect(await screen.findByText(/Default Large Cap Peer/i)).toBeInTheDocument()
  })
})
