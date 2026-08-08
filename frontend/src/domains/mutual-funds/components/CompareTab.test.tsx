import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/utils'
import CompareTab from './CompareTab'
import { apiClient } from '../../../shared/api/client'
import { useAppStore } from '../../../shared/store/appStore'

vi.mock('../../../shared/api/client', () => ({
  apiClient: {
    getHoldings: vi.fn(),
    getPerformance: vi.fn(),
    getBenchmarkHistory: vi.fn(),
    getRollingReturns: vi.fn(),
    searchTicker: vi.fn(),
  },
}))

vi.mock('../../../shared/components/charts/ChartTooltip', () => ({
  ChartTooltip: () => null,
}))

vi.mock('recharts', () => {
  const { createElement, useEffect } = require('react')
  const Passthrough = ({ children }: any) => createElement('div', { 'data-testid': 'chart' }, children)
  const Invoke = (props: Record<string, unknown>) => {
    useEffect(() => {
      const tick = props.tickFormatter as ((v: any) => unknown) | undefined
      if (typeof tick === 'function') {
        tick(15000)
        tick(-12.5)
        tick(0)
      }
      const content = props.content
      if (typeof content === 'function') {
        content({ active: false, payload: [], label: 'Year 0' })
        content({ active: true, payload: [], label: 'Year 0' })
        content({
          active: true,
          payload: [
            { dataKey: 'INF966L01AA3', name: 'Quant', value: 2500000, color: '#6366F1', payload: { rawYear: 5 } },
            { dataKey: 'INF879O01019', name: 'Parag', value: 1800000, color: '#10B981', payload: { rawYear: 5 } },
          ],
          label: 'Year 5',
        })
      }
    }, [])
    return createElement('div', { 'data-testid': 'axis-or-tip' })
  }
  return {
    ResponsiveContainer: Passthrough,
    RadarChart: Passthrough,
    Radar: () => createElement('div'),
    PolarGrid: () => createElement('div'),
    PolarAngleAxis: () => createElement('div'),
    LineChart: Passthrough,
    Line: () => createElement('div'),
    BarChart: Passthrough,
    Bar: () => createElement('div'),
    AreaChart: Passthrough,
    Area: () => createElement('div'),
    XAxis: Invoke,
    YAxis: Invoke,
    CartesianGrid: () => createElement('div'),
    Tooltip: Invoke,
    Legend: () => createElement('div'),
  }
})

const perfFunds = [
  {
    fund: 'Quant Small Cap Fund',
    isin: 'INF966L01AA3',
    alpha: 12.5,
    sharpe: 1.8,
    sortino: 2.1,
    beta: 1.15,
    vol: 16.5,
    consistency: 9,
    fund_xi: 32.4,
    verdict: 'Strong',
    er: 0.75,
    max_dd: -28,
    pe_ratio: 22,
    pb_ratio: 3.1,
    roll_labels: ['1M', '3M', '6M', '1Y', '3Y', '5Y'],
    fund_rolls: [2, 5, 10, 32.4, 28.0, 22.0],
    return_period: 32.4,
  },
  {
    fund: 'Parag Parikh Flexi Cap Fund',
    isin: 'INF879O01019',
    alpha: 6.2,
    sharpe: 1.4,
    sortino: 1.7,
    beta: 0.85,
    vol: 11.2,
    consistency: 8,
    fund_xi: 21.0,
    verdict: 'Strong',
    er: 0.65,
    max_dd: -18,
    pe_ratio: 28,
    pb_ratio: 4.2,
    roll_labels: ['1M', '3M', '6M', '1Y', '3Y', '5Y'],
    fund_rolls: [1, 3, 8, 21.0, 18.0, 15.0],
    return_period: 21.0,
  },
]

describe('CompareTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState({
      mfSessionId: 'sid-compare',
      activeModule: 'mutual_funds',
      compareFunds: { 'sid-compare': ['Quant Small Cap Fund', 'Parag Parikh Flexi Cap Fund'] },
      compareBench: {},
    })
    vi.mocked(apiClient.getHoldings).mockResolvedValue({
      holdings: [
        { Fund: 'Quant Small Cap Fund', ISIN: 'INF966L01AA3', 'Market Value': 400000, 'Day Chg.%': 0.5 },
        { Fund: 'Parag Parikh Flexi Cap Fund', ISIN: 'INF879O01019', 'Market Value': 600000, 'Day Chg.%': -0.2 },
      ],
    } as any)
    vi.mocked(apiClient.getPerformance).mockResolvedValue({
      funds: perfFunds,
      benchmark_return: 14,
      benchmark_stats: {
        alpha: 0,
        beta: 1.0,
        sharpe: 1.1,
        sortino: 1.3,
        volatility: 13.0,
        max_drawdown: -15.0,
        returns: { '1Y': 14, '3Y': 12, '5Y': 11 },
      },
      benchmark_day_chg: 0.3,
    } as any)
    vi.mocked(apiClient.getBenchmarkHistory).mockResolvedValue({
      dates: ['2023-01-01', '2023-06-01', '2023-12-31'],
      values: [100, 115, 130],
    } as any)
    vi.mocked(apiClient.getRollingReturns).mockResolvedValue({
      fund_series: [
        { date: '2023-01-01', value: 12 },
        { date: '2023-06-01', value: 15 },
      ],
    } as any)
    vi.mocked(apiClient.searchTicker).mockResolvedValue({
      results: [{ symbol: 'NIFTYBEES', name: 'Nippon India ETF Nifty BeES' }],
    } as any)
  })

  it('renders section header, portfolio assets autocomplete, and matrix tabs', async () => {
    renderWithProviders(<CompareTab />)

    expect(screen.getByRole('heading', { name: 'Compare Funds' })).toBeInTheDocument()
    expect(screen.getByText('PORTFOLIO ASSETS')).toBeInTheDocument()
    expect(screen.getByText('OTHER MUTUAL FUNDS & INDICES')).toBeInTheDocument()

    expect(await screen.findByText('Comparison Matrix')).toBeInTheDocument()
    expect(screen.getByText('Matrix Overview')).toBeInTheDocument()
    expect(screen.getByText('Deep Technicals')).toBeInTheDocument()
    expect(screen.getByText('Trend Analysis')).toBeInTheDocument()
    expect(screen.getByText('Alpha Leader')).toBeInTheDocument()
  })

  it('handles error state gracefully', async () => {
    const user = userEvent.setup()
    vi.mocked(apiClient.getPerformance).mockRejectedValue(new Error('Fetch failed'))
    renderWithProviders(<CompareTab />)

    expect(await screen.findByText('Data Pipeline Interrupted')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Retry Analytics/i }))
  })

  it('handles 404 session-expired state', async () => {
    vi.mocked(apiClient.getPerformance).mockRejectedValue({
      response: { status: 404 },
    })
    renderWithProviders(<CompareTab />)
    expect(await screen.findByText('Session Expired')).toBeInTheDocument()
    expect(screen.getByText(/re-upload your CAS file/i)).toBeInTheDocument()
  })

  it('switches to Deep Technicals and Trend Analysis tabs including wealth/drawdown', async () => {
    const user = userEvent.setup()
    renderWithProviders(<CompareTab />)
    expect(await screen.findByText('Comparison Matrix')).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: /Deep Technicals/i }))
    expect(screen.getByRole('tab', { name: /Deep Technicals/i })).toHaveAttribute('aria-selected', 'true')
    expect((await screen.findAllByText(/Expense Ratio/i)).length).toBeGreaterThan(0)

    await user.click(screen.getByRole('tab', { name: /Trend Analysis/i }))
    expect(screen.getByRole('tab', { name: /Trend Analysis/i })).toHaveAttribute('aria-selected', 'true')
    expect(await screen.findByText(/Wealth Growth/i)).toBeInTheDocument()

    await user.click(screen.getByText(/Wealth Growth/i))
    expect(await screen.findByText(/Historical compounding of ₹10,000/i)).toBeInTheDocument()

    await user.click(screen.getByText(/Risk Stress Test/i))
    expect(screen.getByText(/Risk Stress Test/i).closest('button')).toHaveAttribute('aria-pressed', 'true')
  })

  it('searches and selects an external market comparator', async () => {
    const user = userEvent.setup()
    renderWithProviders(<CompareTab />)
    expect(await screen.findByText('Comparison Matrix')).toBeInTheDocument()

    const peerInput = screen.getByLabelText(/Search other mutual funds or indices/i)
    await user.type(peerInput, 'NIF')
    await waitFor(() => expect(apiClient.searchTicker).toHaveBeenCalledWith('NIF'), { timeout: 5000 })
    const option = await screen.findByRole('option', { name: /NIFTYBEES/i }, { timeout: 5000 })
    await user.click(option)

    await waitFor(() => {
      expect(useAppStore.getState().compareBench['sid-compare']).toContain('NIFTYBEES')
    })
  })

  it('searches and adds another mutual fund peer to the matrix', async () => {
    const user = userEvent.setup()
    vi.mocked(apiClient.searchTicker).mockResolvedValue({
      results: [{ symbol: '122639', name: 'Parag Parikh Flexi Cap Fund', type: 'Mutual Fund' }],
    } as any)
    vi.mocked(apiClient.getBenchmarkHistory).mockResolvedValue({
      dates: ['2023-01-01', '2023-06-01', '2023-12-31'],
      values: [100, 115, 130],
      returns: { '1Y': 18.5, '3Y': 16.2 },
      sharpe: 1.35,
      sortino: 1.5,
      alpha: 3.2,
      beta: 0.88,
      volatility: 12.4,
      max_drawdown: -14,
      consistency: 7.8,
      ter: 0.76,
      day_chg: 0.4,
    } as any)
    renderWithProviders(<CompareTab />)
    expect(await screen.findByText('Comparison Matrix')).toBeInTheDocument()

    const peerInput = screen.getByLabelText(/Search other mutual funds or indices/i)
    await user.type(peerInput, 'Parag')
    await waitFor(() => expect(apiClient.searchTicker).toHaveBeenCalledWith('Parag'), { timeout: 5000 })
    await user.click(await screen.findByRole('option', { name: /122639/i }, { timeout: 5000 }))

    await waitFor(() => {
      const raw = useAppStore.getState().compareBench['sid-compare']
      expect(raw).toContain('122639')
      expect(raw?.startsWith('[')).toBe(true)
    })
    expect(screen.getAllByText(/Parag Parikh Flexi Cap/i).length).toBeGreaterThan(0)
  })

  it('migrates legacy plain-string compareBench without crashing search', async () => {
    useAppStore.setState({
      compareBench: { 'sid-compare': 'Nifty 50' },
    })
    renderWithProviders(<CompareTab />)
    expect(await screen.findByLabelText(/Search other mutual funds or indices/i)).toBeInTheDocument()
    await waitFor(() => {
      const raw = useAppStore.getState().compareBench['sid-compare']
      expect(raw).toContain('Nifty 50')
      expect(raw?.startsWith('[')).toBe(true)
    })
  })

  it('shows loading skeletons while holdings are fetching', async () => {
    vi.mocked(apiClient.getHoldings).mockReturnValue(new Promise(() => {}) as any)
    renderWithProviders(<CompareTab />)
    await waitFor(() => {
      expect(document.querySelector('.MuiSkeleton-root')).toBeTruthy()
    })
  })

  it('opens SIP sandbox simulator and closes it', async () => {
    const user = userEvent.setup()
    renderWithProviders(<CompareTab />)
    expect(await screen.findByText('Comparison Matrix')).toBeInTheDocument()

    // Sandbox CTA lives under Trend Analysis
    await user.click(await screen.findByRole('button', { name: /Launch Projection Sandbox/i }))
    expect(await screen.findByText(/SIP & Lumpsum Compounding Sandbox/i)).toBeInTheDocument()

    const closeBtns = screen.getAllByTestId('CloseIcon')
    await user.click(closeBtns[closeBtns.length - 1].closest('button')!)
    await waitFor(() => {
      expect(screen.queryByText(/SIP & Lumpsum Compounding Sandbox/i)).not.toBeInTheDocument()
    })
  })

  it('clears selected funds to empty matrix path', async () => {
    useAppStore.setState({
      compareFunds: { 'sid-compare': [] },
    })
    renderWithProviders(<CompareTab />)
    expect(await screen.findByText('PORTFOLIO ASSETS')).toBeInTheDocument()
    expect(screen.queryByText('Comparison Matrix')).not.toBeInTheDocument()
  })

  it('matches funds via fuzzy core-name when ISINs diverge', async () => {
    vi.mocked(apiClient.getPerformance).mockResolvedValue({
      funds: [
        {
          fund: 'Quant Small Cap Direct Growth',
          isin: 'OTHER',
          alpha: 10,
          sharpe: 1.5,
          sortino: 1.6,
          beta: 1.1,
          vol: 18,
          consistency: 8,
          fund_xi: 30,
          verdict: 'Strong',
          er: 0.8,
          roll_labels: ['1Y', '3Y'],
          fund_rolls: [30, 25],
          return_period: 30,
        },
      ],
      benchmark_stats: { alpha: 0, beta: 1, sharpe: 1, sortino: 1, volatility: 12, max_drawdown: -10 },
    } as any)
    useAppStore.setState({
      compareFunds: { 'sid-compare': ['Quant Small Cap Fund'] },
    })
    renderWithProviders(<CompareTab />)
    expect(await screen.findByText('Alpha Leader')).toBeInTheDocument()
    expect(screen.getAllByText(/Quant Small Cap Fund/i).length).toBeGreaterThan(0)
  })

  it('navigates to upload from 404 session-expired CTA', async () => {
    const user = userEvent.setup()
    vi.mocked(apiClient.getPerformance).mockRejectedValue({ response: { status: 404 } })
    const hrefSpy = vi.spyOn(window, 'location', 'get').mockReturnValue({
      ...window.location,
      href: 'http://localhost/mutual-funds',
      assign: vi.fn(),
    } as any)
    // jsdom blocks window.location.href writes; stub via delete+assign pattern
    const orig = window.location
    delete (window as any).location
    ;(window as any).location = { ...orig, href: 'http://localhost/mutual-funds' }

    renderWithProviders(<CompareTab />)
    expect(await screen.findByText('Session Expired')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Go to Upload/i }))
    expect((window as any).location.href).toBe('/')

    ;(window as any).location = orig
    hrefSpy.mockRestore()
  })

  it('updates portfolio selection, shows short-search hint, and clears market peer', async () => {
    const user = userEvent.setup()
    renderWithProviders(<CompareTab />)
    expect(await screen.findByText('Comparison Matrix')).toBeInTheDocument()

    const peerInput = screen.getByLabelText(/Search other mutual funds or indices/i)
    await user.type(peerInput, 'ab')
    expect(await screen.findByText(/Type at least 3 chars/i)).toBeInTheDocument()

    await user.clear(peerInput)
    await user.type(peerInput, 'NIF')
    await waitFor(() => expect(apiClient.searchTicker).toHaveBeenCalledWith('NIF'))
    await user.click(await screen.findByRole('option', { name: /NIFTYBEES/i }))
    await waitFor(() => {
      expect(useAppStore.getState().compareBench['sid-compare']).toContain('NIFTYBEES')
    })

    // Clear the peer selection via the autocomplete clear button
    const clearBtns = screen.getAllByTitle('Clear')
    await user.click(clearBtns[clearBtns.length - 1])
    await waitFor(() => {
      const bench = useAppStore.getState().compareBench['sid-compare']
      expect(!bench || bench === '' || bench === '[]').toBe(true)
    })

    // Deselect one portfolio fund via chip delete
    const chips = screen.getAllByRole('button').filter((b) => b.textContent?.includes('Quant Small Cap Fund'))
    if (chips[0]) {
      const deleteIcon = chips[0].querySelector('[data-testid="CancelIcon"]')
      if (deleteIcon) await user.click(deleteIcon)
    }
  })

  it('covers debt-fund N/A paths, negative metrics, and sandbox sliders', async () => {
    const user = userEvent.setup()
    vi.mocked(apiClient.getHoldings).mockResolvedValue({
      holdings: [
        { Fund: 'Debt Fund A', ISIN: 'INFDEBT00001', 'Market Value': 100000, 'Day Chg.%': -1.25 },
      ],
    } as any)
    vi.mocked(apiClient.getPerformance).mockResolvedValue({
      funds: [
        {
          fund: 'Debt Fund A',
          isin: 'INFDEBT00001',
          alpha: -2.5,
          sharpe: 0.4,
          sortino: 0.5,
          beta: 0.2,
          vol: 3.2,
          consistency: 6,
          fund_xi: 7.1,
          verdict: 'Average',
          er: 0.35,
          max_dd: -4.2,
          is_debt: true,
          roll_labels: ['1Y'],
          fund_rolls: [7.1],
          return_period: 7.1,
        },
      ],
      benchmark_return: 6,
      benchmark_day_chg: -0.4,
      benchmark_stats: {
        alpha: 0,
        beta: 1,
        sharpe: 0.9,
        sortino: 1.0,
        volatility: 8,
        max_drawdown: -12,
        returns: { '1Y': 6, '3Y': 5 },
      },
    } as any)
    useAppStore.setState({
      compareFunds: { 'sid-compare': ['Debt Fund A'] },
      compareBench: {
        'sid-compare': JSON.stringify({ symbol: 'NIFTYBEES', name: 'Nifty BeES' }),
      },
    })

    renderWithProviders(<CompareTab />)
    expect(await screen.findByText('Comparison Matrix')).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: /Deep Technicals/i }))
    expect((await screen.findAllByText(/Expense Ratio/i)).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/N\/A \(Debt\)/i).length).toBeGreaterThan(0)

    await user.click(screen.getByRole('button', { name: /Launch Projection Sandbox/i }))
    expect(await screen.findByText(/SIP & Lumpsum Compounding Sandbox/i)).toBeInTheDocument()

    const sliders = screen.getAllByRole('slider')
    expect(sliders.length).toBeGreaterThanOrEqual(3)
    fireEvent.change(sliders[0], { target: { value: '50000' } })
    fireEvent.change(sliders[1], { target: { value: '1000000' } })
    fireEvent.change(sliders[2], { target: { value: '20' } })
    expect(screen.getByText(/20 Years/i)).toBeInTheDocument()
  })

  it('matches via token-overlap when core names only partially align', async () => {
    vi.mocked(apiClient.getHoldings).mockResolvedValue({
      holdings: [
        { Fund: 'Mirae Asset Large Cap Fund', ISIN: 'INF769K01AX2', 'Market Value': 200000, 'Day Chg.%': 0.1 },
      ],
    } as any)
    vi.mocked(apiClient.getPerformance).mockResolvedValue({
      funds: [
        {
          fund: 'Mirae Asset Large Cap Direct Plan Growth',
          isin: 'DIFFERENT',
          alpha: 3,
          sharpe: 1.1,
          sortino: 1.2,
          beta: 0.95,
          vol: 12,
          consistency: 7,
          fund_xi: 15,
          verdict: 'Average',
          er: 0.5,
          roll_labels: ['1Y', '3Y'],
          fund_rolls: [15, 14],
          return_period: 15,
        },
      ],
      benchmark_stats: { alpha: 0, beta: 1, sharpe: 1, sortino: 1, volatility: 11, max_drawdown: -10 },
    } as any)
    useAppStore.setState({
      compareFunds: { 'sid-compare': ['Mirae Asset Large Cap Fund'] },
      compareBench: {},
    })
    renderWithProviders(<CompareTab />)
    expect(await screen.findByText('Alpha Leader')).toBeInTheDocument()
  })
})
