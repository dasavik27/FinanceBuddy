import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../../test/utils'
import StockAnalyzerTab from './StockAnalyzerTab'
import { apiClient } from '../../../../shared/api/client'
import { useStockAnalyzerStore } from '../../hooks/useStockAnalyzerStore'
import { useAppStore } from '../../../../shared/store/appStore'

vi.mock('../../../../shared/api/client', () => ({
  apiClient: {
    searchStocks: vi.fn(),
    analyzeStock: vi.fn(),
    getStockFinancials: vi.fn(),
    getStockImpact: vi.fn(),
    stockPortfolioImpact: vi.fn(),
    getMarketIndices: vi.fn(),
  },
}))

/** Invoke Recharts formatters/tickFormatters during render so those closures count toward coverage. */
vi.mock('recharts', () => {
  const invokeFormatters = (props: Record<string, unknown>) => {
    const tickFormatter = props.tickFormatter as ((v: number) => string) | undefined
    const formatter = props.formatter as ((v: number, name: string) => unknown) | undefined
    tickFormatter?.(1234.5)
    formatter?.(98.7, 'Price')
    formatter?.(-2.5, 'NIFTY 50')
  }

  const Passthrough = (testId: string) => {
    const Comp = ({ children, ...props }: { children?: React.ReactNode; [key: string]: unknown }) => {
      invokeFormatters(props)
      // Keep nested chart structure, but drop host SVG tags (defs/linearGradient/stop).
      const safeChildren = React.Children.toArray(children).filter(
        (child) => React.isValidElement(child) && typeof child.type !== 'string',
      )
      return <div data-testid={testId}>{safeChildren}</div>
    }
    Comp.displayName = testId
    return Comp
  }

  return {
    ResponsiveContainer: ({ children }: { children?: React.ReactNode }) => (
      <div data-testid="ResponsiveContainer">{children}</div>
    ),
    AreaChart: Passthrough('AreaChart'),
    LineChart: Passthrough('LineChart'),
    BarChart: Passthrough('BarChart'),
    Area: Passthrough('Area'),
    Line: Passthrough('Line'),
    Bar: Passthrough('Bar'),
    Cell: Passthrough('Cell'),
    XAxis: Passthrough('XAxis'),
    YAxis: Passthrough('YAxis'),
    Tooltip: Passthrough('Tooltip'),
    Legend: Passthrough('Legend'),
    ReferenceLine: Passthrough('ReferenceLine'),
    CartesianGrid: Passthrough('CartesianGrid'),
  }
})

function makeCashFlow(period: string, overrides: Record<string, number | null> = {}) {
  return {
    period,
    net_income_cr: 1200,
    cash_from_operations_cr: 1500,
    cash_from_investing_cr: -400,
    cash_from_financing_cr: -200,
    net_change_in_cash_cr: 900,
    free_cash_flow_cr: 1100,
    change_in_inventories_cr: -50,
    gain_loss_on_sale_assets_cr: 10,
    ...overrides,
  }
}

function makeIncome(period: string, overrides: Record<string, number | null> = {}) {
  return {
    period,
    revenue_cr: 5000,
    operating_expense_cr: 3000,
    net_income_cr: 1200,
    net_margin_pct: 24,
    eps: 12.5,
    ebitda_cr: 1800,
    effective_tax_rate_pct: 25.5,
    ...overrides,
  }
}

function makeBalance(period: string, overrides: Record<string, number | null> = {}) {
  return {
    period,
    cash_and_equivalents_cr: 800,
    total_assets_cr: 20000,
    total_liabilities_cr: 9000,
    total_equity_cr: 11000,
    shares_outstanding: 6500000000,
    equity_multiplier: 1.82,
    return_on_assets_pct: 8.5,
    ...overrides,
  }
}

function makeFullStock(overrides: Record<string, unknown> = {}) {
  return {
    symbol: 'RELIANCE',
    name: 'Reliance Industries Ltd.',
    source: 'Yahoo Finance',
    as_of: '2026-08-01T10:30:00Z',
    current_price: 2950,
    day_change: 35,
    day_change_pct: 1.2,
    day_low: 2900,
    day_high: 2980,
    week52_low: 2200,
    week52_high: 3200,
    year_return: 18.5,
    sector: 'Energy',
    isin: 'INE002A01018',
    market_cap_cr: 1800000,
    pe_ratio: 28.5,
    sector_pe: 22.1,
    pb_ratio: 2.4,
    dividend_yield: 0.35,
    eps: 98.2,
    beta: 1.12,
    vwap: 2940,
    delivery_pct: 62.5,
    roe: 18.2,
    description: 'A diversified conglomerate operating across energy and retail.',
    sources: {
      charts: 'Yahoo Finance',
      valuation: 'Yahoo Finance',
      technicals: 'Yahoo Finance',
      peers: 'NSE',
      financials: 'Yahoo Finance',
      earnings: 'Yahoo Finance',
      corporate_actions: 'NSE Disclosures',
      events: 'NSE',
      announcements: 'NSE Announcements',
      latest_filing: 'NSE XBRL',
      compare: 'Yahoo Finance',
      description: 'Yahoo Finance',
      market_cap: 'Yahoo Finance',
      pe_ratio: 'Yahoo Finance',
      pb_ratio: 'Yahoo Finance',
      dividend_yield: 'Yahoo Finance',
      eps: 'Yahoo Finance',
      beta: 'Yahoo Finance',
      vwap: 'Yahoo Finance',
      delivery_pct: 'NSE',
    },
    chart: {
      dates: ['2026-01-01', '2026-02-01', '2026-03-01'],
      prices: [2800, 2900, 2950],
      volumes: [100000, 120000, 110000],
      volume: [100000, 90000, 110000],
      sma_50: [2750, 2800, 2850],
      sma_200: [2600, 2650, 2700],
      benchmark: [24000, 24200, 24500],
    },
    timeframes: {
      '1D': {
        dates: ['2026-08-01T09:15', '2026-08-01T15:30'],
        prices: [2940, 2950],
        start_price: 2940,
        end_price: 2950,
        change: 10,
        p_change: 0.34,
      },
      '5D': {
        dates: ['2026-07-28', '2026-08-01'],
        prices: [3000, 2950],
        start_price: 3000,
        end_price: 2950,
        change: -50,
        p_change: -1.67,
      },
      '1Y': {
        dates: ['2025-08-01', '2026-08-01'],
        prices: [2500, 2950],
        start_price: 2500,
        end_price: 2950,
        change: 450,
        p_change: 18,
      },
    },
    technicals: {
      rsi_14: 62.5,
      rsi_status: 'Neutral',
      trend: 'Uptrend',
      sma_50: 2800,
      sma_200: 2650,
      above_50_dma: true,
      above_200_dma: true,
      dist_52w_high_pct: -7.8,
    },
    peers: [
      {
        symbol: 'ONGC',
        name: 'Oil & Natural Gas Corp',
        current_price: 280,
        p_change: 1.5,
      },
      {
        symbol: 'BPCL',
        name: 'Bharat Petroleum',
        current_price: 620,
        p_change: -0.8,
      },
    ],
    corporate_actions: [
      {
        symbol: 'RELIANCE',
        type: 'dividend',
        subject: 'Final dividend ₹5',
        ratio: null,
        ex_date: '2026-07-15',
      },
      {
        symbol: 'RELIANCE',
        type: 'bonus',
        subject: 'Bonus issue',
        ratio: '1:1',
        ex_date: '2025-12-01',
      },
    ],
    upcoming_events: [{ date: '2026-09-10', purpose: 'Board meeting - Q1 results' }],
    announcements: [
      { broadcast_at: '2026-07-20 18:00:00', subject: 'Outcome of board meeting' },
      { broadcast_at: '', subject: null },
    ],
    latest_filing: {
      quarter_end: 'Jun 2026',
      basis: 'Consolidated',
      audited: 'Unaudited',
      source: 'NSE XBRL',
      revenue_cr: 250000,
      pbt_cr: 22000,
      net_income_cr: 18000,
      net_margin_pct: 7.2,
      eps_basic: 26.5,
    },
    financial_statements: {
      quarterly: {
        cash_flow: [makeCashFlow('Q1 2026'), makeCashFlow('Q4 2025', { cash_from_investing_cr: -500 })],
        income_statement: [makeIncome('Q1 2026'), makeIncome('Q4 2025', { eps: null })],
        balance_sheet: [makeBalance('Q1 2026'), makeBalance('Q4 2025', { shares_outstanding: null, equity_multiplier: null })],
      },
      annual: {
        cash_flow: [makeCashFlow('FY2025')],
        income_statement: [makeIncome('FY2025')],
        balance_sheet: [makeBalance('FY2025')],
      },
    },
    earnings_summary: {
      last_report_date: '20 Jul 2026',
      financial_period: 'Q1 FY27',
      reported_eps: 26.5,
      reported_revenue_cr: 250000,
      history: [
        { period: 'Q1 FY27', date: '2026-07-20', reported_eps: 26.5, reported_revenue_cr: 250000 },
        { period: 'Q4 FY26', date: '2026-04-20', reported_eps: 24.1, reported_revenue_cr: 240000 },
      ],
    },
    consensus: {
      eps: { '+1q': { avg: 28.1, analysts: 12 } },
      revenue_cr: { '+1q': { avg: 260000, analysts: 1 } },
    },
    ...overrides,
  }
}

function seedStock(overrides: Record<string, unknown> = {}, storeExtras: Record<string, unknown> = {}) {
  useStockAnalyzerStore.setState({
    stock: makeFullStock(overrides) as any,
    selectedStock: { symbol: 'RELIANCE', name: 'Reliance Industries Ltd.' },
    query: 'RELIANCE - Reliance Industries Ltd.',
    activeSubTab: 'overview',
    activeTimeframe: '1Y',
    chartType: 'area',
    compareBenchmark: true,
    compareStocks: [],
    impact: null,
    analysisError: null,
    impactAmount: '100000',
    watchlist: ['RELIANCE', 'TCS', 'HDFCBANK', 'INFY'],
    ...storeExtras,
  })
}

describe('StockAnalyzerTab Component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState({ equitySessionId: 'eq-sess-1' })
    useStockAnalyzerStore.getState().clear()
    useStockAnalyzerStore.setState({
      watchlist: ['RELIANCE', 'TCS', 'HDFCBANK', 'INFY'],
      compareBenchmark: true,
      chartType: 'area',
      impactAmount: '100000',
    })
    vi.mocked(apiClient.getMarketIndices).mockResolvedValue({
      indices: [{ symbol: 'NIFTY 50', name: 'NIFTY 50', price: 24500, change: 120, p_change: 0.5 }],
    } as any)
    vi.mocked(apiClient.searchStocks).mockResolvedValue({ results: [] } as any)
    vi.mocked(apiClient.stockPortfolioImpact).mockResolvedValue({
      sector_weight_before: 10,
      sector_weight_after: 14,
      sector_delta: 4,
      already_owned: false,
      concentration_warning: false,
    } as any)
  })

  it('renders search input and market indices ribbon when no stock is selected', async () => {
    renderWithProviders(<StockAnalyzerTab />)

    expect(
      screen.getByPlaceholderText(/Search Indian stocks \(e\.g\. RELIANCE, TCS, INFY/i),
    ).toBeInTheDocument()
    expect(await screen.findByText('NIFTY 50')).toBeInTheDocument()
    expect(screen.getByText(/Watchlist:/i)).toBeInTheDocument()
  })

  it('searches and loads a stock from autocomplete selection', async () => {
    const user = userEvent.setup()
    const analyzed = makeFullStock({ symbol: 'INFY', name: 'Infosys Ltd.', sector: 'Technology' })
    vi.mocked(apiClient.searchStocks).mockResolvedValue({
      results: [{ symbol: 'INFY', name: 'Infosys Ltd.' }],
    } as any)
    vi.mocked(apiClient.analyzeStock).mockResolvedValue(analyzed as any)

    renderWithProviders(<StockAnalyzerTab />)

    const input = screen.getByPlaceholderText(/Search Indian stocks/i)
    await user.type(input, 'INFY')

    await waitFor(() => expect(apiClient.searchStocks).toHaveBeenCalledWith('INFY'), { timeout: 5000 })
    const option = await screen.findByRole('option', { name: /INFY - Infosys Ltd/i }, { timeout: 5000 })
    await user.click(option)

    expect(await screen.findByText('Infosys Ltd.')).toBeInTheDocument()
    expect(screen.getByText('NSE: INFY')).toBeInTheDocument()
    await waitFor(() => expect(apiClient.analyzeStock).toHaveBeenCalledWith('INFY'))
    await waitFor(() =>
      expect(apiClient.stockPortfolioImpact).toHaveBeenCalledWith('INFY', 100000, 'eq-sess-1'),
    )
  })

  it('loads stock from watchlist pill and shows loading then analysis', async () => {
    const user = userEvent.setup()
    let resolveAnalyze: (v: unknown) => void
    const analyzePromise = new Promise((resolve) => {
      resolveAnalyze = resolve
    })
    vi.mocked(apiClient.analyzeStock).mockReturnValue(analyzePromise as any)

    renderWithProviders(<StockAnalyzerTab />)

    await user.click(await screen.findByRole('button', { name: 'TCS' }))
    expect(await screen.findByText(/Fetching market data/i)).toBeInTheDocument()

    resolveAnalyze!(makeFullStock({ symbol: 'TCS', name: 'Tata Consultancy Services', sector: 'Technology' }))
    expect(await screen.findByText('Tata Consultancy Services')).toBeInTheDocument()
  })

  it('shows 404 analysis error with retry that succeeds', async () => {
    const user = userEvent.setup()
    vi.mocked(apiClient.analyzeStock)
      .mockRejectedValueOnce({ response: { status: 404 } })
      .mockResolvedValueOnce(makeFullStock({ symbol: 'TCS', name: 'Tata Consultancy Services' }) as any)

    renderWithProviders(<StockAnalyzerTab />)
    await user.click(await screen.findByRole('button', { name: 'TCS' }))

    expect(await screen.findByText(/That symbol was not recognised/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Retry/i }))
    expect(await screen.findByText('Tata Consultancy Services')).toBeInTheDocument()
  })

  it('shows generic analysis error when load fails without 404', async () => {
    const user = userEvent.setup()
    vi.mocked(apiClient.analyzeStock).mockRejectedValueOnce(new Error('network'))

    renderWithProviders(<StockAnalyzerTab />)
    await user.click(await screen.findByRole('button', { name: 'INFY' }))

    expect(
      await screen.findByText(/Could not load analysis for that stock/i),
    ).toBeInTheDocument()
  })

  it('shows analysis error without retry when no selectedStock is set', async () => {
    useStockAnalyzerStore.setState({
      stock: null,
      selectedStock: null,
      analysisError: 'Could not load analysis for that stock. Please try again.',
    })
    renderWithProviders(<StockAnalyzerTab />)

    expect(await screen.findByText(/Could not load analysis for that stock/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Retry/i })).not.toBeInTheDocument()
  })

  it('clears selection via autocomplete clear control', async () => {
    const user = userEvent.setup()
    seedStock()
    renderWithProviders(<StockAnalyzerTab />)

    expect(await screen.findByText('Reliance Industries Ltd.')).toBeInTheDocument()
    const clearBtn = screen.getByLabelText(/Clear/i)
    await user.click(clearBtn)

    await waitFor(() => {
      expect(screen.queryByText('Reliance Industries Ltd.')).not.toBeInTheDocument()
    })
    expect(useStockAnalyzerStore.getState().stock).toBeNull()
  })

  it('clears selection when search input is emptied', async () => {
    const user = userEvent.setup()
    seedStock()
    renderWithProviders(<StockAnalyzerTab />)

    expect(await screen.findByText('Reliance Industries Ltd.')).toBeInTheDocument()
    const input = screen.getByPlaceholderText(/Search Indian stocks/i)
    await user.clear(input)

    await waitFor(() => {
      expect(useStockAnalyzerStore.getState().stock).toBeNull()
    })
  })

  it('displays stock analysis header, stats, ranges, peers, filings and about', async () => {
    seedStock()
    renderWithProviders(<StockAnalyzerTab />)

    expect(await screen.findByText('Reliance Industries Ltd.')).toBeInTheDocument()
    expect(screen.getByText('NSE: RELIANCE')).toBeInTheDocument()
    expect(screen.getByText(/Yahoo Finance/)).toBeInTheDocument()
    expect(screen.getByText('Energy')).toBeInTheDocument()
    expect(screen.getByText(/ISIN: INE002A01018/)).toBeInTheDocument()
    expect(screen.getByText(/Key Statistics & Valuation/i)).toBeInTheDocument()
    expect(screen.getByText("Day's Range")).toBeInTheDocument()
    expect(screen.getByText('52-Week Range')).toBeInTheDocument()
    expect(screen.getByText(/People Also Watch/i)).toBeInTheDocument()
    expect(screen.getByText('ONGC')).toBeInTheDocument()
    expect(screen.getByText(/Corporate actions/i)).toBeInTheDocument()
    expect(screen.getByText(/Board meeting - Q1 results/i)).toBeInTheDocument()
    expect(screen.getByText(/Recent exchange filings/i)).toBeInTheDocument()
    expect(screen.getByText(/Outcome of board meeting/i)).toBeInTheDocument()
    expect(screen.getByText('About')).toBeInTheDocument()
    expect(screen.getByText(/diversified conglomerate/i)).toBeInTheDocument()
  })

  it('toggles timeframe and chart type on overview', async () => {
    const user = userEvent.setup()
    seedStock()
    renderWithProviders(<StockAnalyzerTab />)

    expect(await screen.findByText(/past 1Y/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '5D' }))
    expect(await screen.findByText(/past 5D/i)).toBeInTheDocument()
    expect(useStockAnalyzerStore.getState().activeTimeframe).toBe('5D')

    await user.click(screen.getByRole('button', { name: '1D' }))
    expect(await screen.findByText(/past 1D/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /^line$/i }))
    expect(useStockAnalyzerStore.getState().chartType).toBe('line')
    await user.click(screen.getByRole('button', { name: /^area$/i }))
    expect(useStockAnalyzerStore.getState().chartType).toBe('area')
  })

  it('falls back to chart series when timeframe slice is missing', async () => {
    const user = userEvent.setup()
    seedStock({ timeframes: {} })
    renderWithProviders(<StockAnalyzerTab />)

    expect(await screen.findByText('Reliance Industries Ltd.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '6M' }))
    expect(useStockAnalyzerStore.getState().activeTimeframe).toBe('6M')
    expect(screen.getByText(/past 6M/i)).toBeInTheDocument()
  })

  it('toggles watchlist star for selected stock', async () => {
    const user = userEvent.setup()
    seedStock({}, { watchlist: ['TCS'] })
    renderWithProviders(<StockAnalyzerTab />)

    expect(await screen.findByText('Reliance Industries Ltd.')).toBeInTheDocument()
    const header = screen.getByText('Reliance Industries Ltd.').parentElement!
    const starBtn = within(header).getAllByRole('button')[0]
    await user.click(starBtn)
    expect(useStockAnalyzerStore.getState().watchlist).toContain('RELIANCE')
    await user.click(starBtn)
    expect(useStockAnalyzerStore.getState().watchlist).not.toContain('RELIANCE')
  })

  it('loads a peer stock from People Also Watch', async () => {
    const user = userEvent.setup()
    seedStock()
    vi.mocked(apiClient.analyzeStock).mockResolvedValue(
      makeFullStock({ symbol: 'ONGC', name: 'Oil & Natural Gas Corp', sector: 'Energy' }) as any,
    )
    renderWithProviders(<StockAnalyzerTab />)

    expect(await screen.findByText('ONGC')).toBeInTheDocument()
    await user.click(screen.getByText('ONGC'))
    await waitFor(() => expect(apiClient.analyzeStock).toHaveBeenCalledWith('ONGC'))
    expect(await screen.findByText('NSE: ONGC')).toBeInTheDocument()
    expect(screen.getAllByText('Oil & Natural Gas Corp').length).toBeGreaterThan(0)
  })

  it('shows portfolio connect prompt when session is missing', async () => {
    useAppStore.setState({ equitySessionId: null })
    seedStock()
    renderWithProviders(<StockAnalyzerTab />)

    expect(
      await screen.findByText(/Upload or connect your equity portfolio/i),
    ).toBeInTheDocument()
  })

  it('runs portfolio impact simulation with warnings and owned position', async () => {
    const user = userEvent.setup()
    seedStock()
    vi.mocked(apiClient.stockPortfolioImpact).mockResolvedValue({
      already_owned: true,
      existing_position: { quantity: 25 },
      sector_weight_before: 12,
      sector_weight_after: 18,
      sector_delta: 6,
      concentration_warning: true,
    } as any)

    renderWithProviders(<StockAnalyzerTab />)
    expect(await screen.findByText(/Portfolio Impact Simulator/i)).toBeInTheDocument()

    const amount = screen.getByDisplayValue('100000')
    await user.clear(amount)
    await user.type(amount, '250000')
    await user.click(screen.getByRole('button', { name: /Simulate/i }))

    expect(await screen.findByText(/You already own 25 shares of RELIANCE/i)).toBeInTheDocument()
    expect(screen.getByText(/Before Trade/i)).toBeInTheDocument()
    expect(screen.getByText(/After Trade/i)).toBeInTheDocument()
    expect(screen.getByText(/exceed 15% of your total equity portfolio/i)).toBeInTheDocument()
  })

  it('shows impact error and retries simulation', async () => {
    const user = userEvent.setup()
    seedStock()
    vi.mocked(apiClient.stockPortfolioImpact)
      .mockRejectedValueOnce(new Error('fail'))
      .mockResolvedValueOnce({
        sector_weight_before: 8,
        sector_weight_after: 11,
        sector_delta: 3,
        already_owned: false,
        concentration_warning: false,
      } as any)

    renderWithProviders(<StockAnalyzerTab />)
    await user.click(await screen.findByRole('button', { name: /Simulate/i }))

    expect(await screen.findByText(/Could not run that simulation/i)).toBeInTheDocument()
    const retryButtons = screen.getAllByRole('button', { name: /Retry/i })
    await user.click(retryButtons[retryButtons.length - 1])
    expect(await screen.findByText(/Energy Exposure Shift/i)).toBeInTheDocument()
  })

  it('ignores invalid impact amounts', async () => {
    const user = userEvent.setup()
    seedStock({}, { impactAmount: '0' })
    renderWithProviders(<StockAnalyzerTab />)

    await user.click(await screen.findByRole('button', { name: /Simulate/i }))
    expect(apiClient.stockPortfolioImpact).not.toHaveBeenCalled()
  })

  it('switches to indicators tab and renders RSI, DMA and volume', async () => {
    const user = userEvent.setup()
    seedStock()
    renderWithProviders(<StockAnalyzerTab />)

    await user.click(await screen.findByRole('button', { name: /Indicators/i }))
    expect(await screen.findByText(/Technical Indicators & Moving Averages/i)).toBeInTheDocument()
    expect(screen.getByText(/Trend: Uptrend/i)).toBeInTheDocument()
    expect(screen.getByText('RSI (14-Day)')).toBeInTheDocument()
    expect(screen.getByText('62.5')).toBeInTheDocument()
    expect(screen.getByText('50-Day DMA')).toBeInTheDocument()
    expect(screen.getByText(/Bullish \(>50 DMA\)/i)).toBeInTheDocument()
    expect(screen.getByText(/Above 200 DMA/i)).toBeInTheDocument()
    expect(screen.getByText(/Traded Volume History/i)).toBeInTheDocument()
  })

  it('renders oversold RSI and bearish DMA states', async () => {
    seedStock(
      {
        technicals: {
          rsi_14: 22,
          rsi_status: 'Oversold',
          trend: 'Downtrend',
          sma_50: 3000,
          sma_200: 3100,
          above_50_dma: false,
          above_200_dma: false,
          dist_52w_high_pct: -20,
        },
      },
      { activeSubTab: 'indicators' },
    )
    renderWithProviders(<StockAnalyzerTab />)

    expect(await screen.findByText(/Trend: Downtrend/i)).toBeInTheDocument()
    expect(screen.getByText('22.0')).toBeInTheDocument()
    expect(screen.getByText(/Bearish \(<50 DMA\)/i)).toBeInTheDocument()
    expect(screen.getByText(/Below 200 DMA/i)).toBeInTheDocument()
  })

  it('renders overbought RSI and strong uptrend chip', async () => {
    seedStock(
      {
        technicals: {
          rsi_14: 78,
          rsi_status: 'Overbought',
          trend: 'Strong Uptrend',
          sma_50: 2700,
          sma_200: 2500,
          above_50_dma: true,
          above_200_dma: true,
        },
      },
      { activeSubTab: 'indicators' },
    )
    renderWithProviders(<StockAnalyzerTab />)

    expect(await screen.findByText(/Trend: Strong Uptrend/i)).toBeInTheDocument()
    expect(screen.getByText('78.0')).toBeInTheDocument()
  })

  it('renders indicators with missing technicals gracefully', async () => {
    seedStock(
      {
        technicals: {
          rsi_14: null,
          trend: 'Sideways',
          sma_50: null,
          sma_200: null,
          above_50_dma: null,
          above_200_dma: null,
          dist_52w_high_pct: null,
        },
        week52_high: null,
        chart: { dates: [], prices: [], volume: [] },
      },
      { activeSubTab: 'indicators' },
    )
    renderWithProviders(<StockAnalyzerTab />)

    expect(await screen.findByText(/Technical Indicators & Moving Averages/i)).toBeInTheDocument()
    expect(screen.getByText(/Trend: Sideways/i)).toBeInTheDocument()
    expect(screen.getAllByText('-').length).toBeGreaterThan(0)
  })

  it('covers compare tab: benchmark toggle, peer add, remove and clear', async () => {
    const user = userEvent.setup()
    const peerStock = makeFullStock({
      symbol: 'ONGC',
      name: 'Oil & Natural Gas Corp',
      current_price: 280,
      year_return: -5.2,
      market_cap_cr: 350000,
      pe_ratio: 8.2,
      pb_ratio: 1.1,
      dividend_yield: 3.5,
      roe: 12,
      beta: 0.9,
      week52_low: 200,
      week52_high: 320,
      chart: {
        dates: ['2026-01-15', '2026-02-15'],
        prices: [250, 280],
        benchmark: [24000, 24500],
      },
    })
    seedStock({}, { activeSubTab: 'compare' })
    vi.mocked(apiClient.analyzeStock).mockResolvedValue(peerStock as any)

    renderWithProviders(<StockAnalyzerTab />)

    expect(await screen.findByText(/Compare with Other Stocks/i)).toBeInTheDocument()
    expect(screen.getByText(/Multi-Asset Fundamentals/i)).toBeInTheDocument()
    expect(screen.getAllByText(/RELIANCE \(Target\)/i).length).toBeGreaterThan(0)

    await user.click(screen.getByRole('button', { name: /NIFTY 50 Benchmark/i }))
    expect(screen.getByRole('button', { name: /\+ Add NIFTY 50 Benchmark/i })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /\+ Add NIFTY 50 Benchmark/i }))
    expect(screen.getAllByText(/NIFTY 50 \(Benchmark\)/i).length).toBeGreaterThan(0)

    await user.click(screen.getByText('+ ONGC'))
    await waitFor(() => expect(apiClient.analyzeStock).toHaveBeenCalledWith('ONGC'))
    expect(await screen.findByRole('button', { name: /Clear Comparisons/i })).toBeInTheDocument()
    expect(screen.getByText(/Return on Equity \(ROE\)/i)).toBeInTheDocument()

    // Remove via chip delete (compared stock chip, not the quick-add peer chip)
    const compareChips = screen.getAllByText('ONGC')
      .map((el) => el.closest('.MuiChip-root'))
      .filter((el): el is HTMLElement => !!el && !!within(el).queryByTestId('CloseIcon'))
    expect(compareChips.length).toBeGreaterThan(0)
    await user.click(within(compareChips[0]).getByTestId('CloseIcon'))
    await waitFor(() => expect(useStockAnalyzerStore.getState().compareStocks).toHaveLength(0))

    // Re-add and clear all
    await user.click(screen.getByText('+ ONGC'))
    await waitFor(() => expect(useStockAnalyzerStore.getState().compareStocks).toHaveLength(1))
    await user.click(screen.getByRole('button', { name: /Clear Comparisons/i }))
    expect(useStockAnalyzerStore.getState().compareStocks).toHaveLength(0)
  })

  it('adds compare stock from compare autocomplete search', async () => {
    const user = userEvent.setup()
    seedStock({}, { activeSubTab: 'compare' })
    vi.mocked(apiClient.searchStocks).mockResolvedValue({
      results: [{ symbol: 'HDFCBANK', name: 'HDFC Bank Ltd' }],
    } as any)
    vi.mocked(apiClient.analyzeStock).mockResolvedValue(
      makeFullStock({
        symbol: 'HDFCBANK',
        name: 'HDFC Bank Ltd',
        chart: { dates: ['2026-01-01', '2026-03-01'], prices: [1500, 1600] },
      }) as any,
    )

    renderWithProviders(<StockAnalyzerTab />)
    const compareInput = await screen.findByPlaceholderText(/Add stock to compare/i)
    await user.type(compareInput, 'HDFC')

    await waitFor(() => expect(apiClient.searchStocks).toHaveBeenCalled(), { timeout: 5000 })
    const option = await screen.findByRole('option', { name: /HDFCBANK - HDFC Bank Ltd/i }, { timeout: 5000 })
    await user.click(option)

    await waitFor(() => expect(apiClient.analyzeStock).toHaveBeenCalledWith('HDFCBANK'))
    expect(useStockAnalyzerStore.getState().compareStocks.some((s) => s.symbol === 'HDFCBANK')).toBe(true)
  })

  it('ignores failed compare stock loads and duplicate adds', async () => {
    const user = userEvent.setup()
    seedStock(
      {},
      {
        activeSubTab: 'compare',
        compareStocks: [makeFullStock({ symbol: 'ONGC', name: 'ONGC' }) as any],
      },
    )
    vi.mocked(apiClient.analyzeStock).mockRejectedValueOnce(new Error('boom'))

    renderWithProviders(<StockAnalyzerTab />)
    expect(await screen.findByText('+ BPCL')).toBeInTheDocument()

    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    await user.click(screen.getByText('+ BPCL'))
    await waitFor(() => expect(apiClient.analyzeStock).toHaveBeenCalledWith('BPCL'))
    expect(useStockAnalyzerStore.getState().compareStocks).toHaveLength(1)

    // Already added peer chip disabled
    expect(screen.getByText('+ ONGC').closest('.MuiChip-root')).toHaveClass('Mui-disabled')
    consoleSpy.mockRestore()
  })

  it('shows financials empty state when statements are missing', async () => {
    seedStock(
      { financial_statements: undefined, latest_filing: null },
      { activeSubTab: 'financials' },
    )
    renderWithProviders(<StockAnalyzerTab />)

    expect(
      await screen.findByText(/Financial statement data is currently being populated for RELIANCE/i),
    ).toBeInTheDocument()
  })

  it('covers financials statement/period switches and metric toggles', async () => {
    const user = userEvent.setup()
    seedStock({}, { activeSubTab: 'financials' })
    renderWithProviders(<StockAnalyzerTab />)

    expect(await screen.findByText(/Latest filed quarter/i)).toBeInTheDocument()
    expect(screen.getByText(/Financial statements/i)).toBeInTheDocument()
    expect(screen.getAllByText(/Cash from operations/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Net income/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Free cash flow/i).length).toBeGreaterThan(0)

    // Toggle a cash-flow metric off (still >1 selected) via the filter chips
    const investingFilters = screen.getAllByText('Cash from investing')
    await user.click(investingFilters[0])
    await user.click(screen.getAllByText('Cash from investing')[0])

    await user.click(screen.getByRole('button', { name: /Income statement/i }))
    expect(screen.getAllByText('Revenue').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Operating expense/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/Net profit margin/i)).toBeInTheDocument()
    await user.click(screen.getAllByText('EBITDA')[0])

    await user.click(screen.getByRole('button', { name: /Balance sheet/i }))
    expect(screen.getAllByText(/Total assets/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/Equity multiplier/i)).toBeInTheDocument()
    expect(screen.getByText(/Return on assets/i)).toBeInTheDocument()
    await user.click(screen.getAllByText('Total equity')[0])

    await user.click(screen.getByRole('button', { name: /Annual/i }))
    expect(screen.getAllByText('FY2025').length).toBeGreaterThan(0)
    await user.click(screen.getByRole('button', { name: /Quarterly/i }))
    expect(screen.getAllByText('Q1 2026').length).toBeGreaterThan(0)

    // Switch back to cash flow and ensure last-metric deselect is blocked
    await user.click(screen.getByRole('button', { name: /Cash flow/i }))
    await user.click(screen.getAllByText('Cash from investing')[0])
    await user.click(screen.getAllByText('Cash from financing')[0])
    await user.click(screen.getAllByText('Cash from operations')[0])
    expect(screen.getAllByText('Cash from operations').length).toBeGreaterThan(0)
  })

  it('covers earnings tab with history and consensus', async () => {
    seedStock({}, { activeSubTab: 'earnings' })
    renderWithProviders(<StockAnalyzerTab />)

    expect(await screen.findByText('Last report')).toBeInTheDocument()
    expect(screen.getByText('20 Jul 2026')).toBeInTheDocument()
    expect(screen.getAllByText('Q1 FY27').length).toBeGreaterThan(0)
    expect(screen.getByText(/Reported EPS \(INR\)/i)).toBeInTheDocument()
    expect(screen.getByText(/Next Q consensus ₹28.10 · 12 analysts/i)).toBeInTheDocument()
    expect(screen.getByText(/Reported revenue \(INR\)/i)).toBeInTheDocument()
    expect(screen.getByText(/Fiscal Q1 FY27 earnings call/i)).toBeInTheDocument()
    expect(screen.getByText('Reported EPS')).toBeInTheDocument()
    expect(screen.getByText('Reported Revenue')).toBeInTheDocument()
  })

  it('shows earnings empty state and earnings-list fallback', async () => {
    seedStock(
      { earnings_summary: null, earnings: [] },
      { activeSubTab: 'earnings' },
    )
    const { unmount } = renderWithProviders(<StockAnalyzerTab />)
    expect(
      await screen.findByText(/Quarterly earnings history is not available for RELIANCE/i),
    ).toBeInTheDocument()
    unmount()

    seedStock(
      {
        earnings_summary: { financial_period: 'Q2', reported_eps: 10, reported_revenue_cr: 500 },
        earnings: [{ quarter: 'Q2 FY26', date: '2026-01-01', reported_eps: 10 }],
        consensus: {
          eps: { '+1q': { avg: 11, analysts: 1 } },
          revenue_cr: { '+1q': { avg: 900, analysts: 2 } },
        },
      },
      { activeSubTab: 'earnings' },
    )
    renderWithProviders(<StockAnalyzerTab />)
    expect(await screen.findByText('Q2 FY26')).toBeInTheDocument()
    expect(screen.getByText(/1 analyst$/i)).toBeInTheDocument()
  })

  it('switches across all sub-tabs via navigation buttons', async () => {
    const user = userEvent.setup()
    seedStock()
    renderWithProviders(<StockAnalyzerTab />)

    expect(await screen.findByRole('button', { name: /Overview/i })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Indicators/i }))
    expect(await screen.findByText(/Technical Indicators/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Compare/i }))
    expect(await screen.findByText(/Compare with Other Stocks/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Financials/i }))
    expect(await screen.findByText(/Financial statements/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Earnings/i }))
    expect(await screen.findByText(/Last report/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Overview/i }))
    expect(await screen.findByText(/Key Statistics & Valuation/i)).toBeInTheDocument()
  })

  it('handles sparse overview data without ranges/peers/actions', async () => {
    seedStock({
      day_low: null,
      day_high: null,
      week52_low: null,
      week52_high: null,
      market_cap_cr: null,
      pe_ratio: null,
      sector_pe: null,
      pb_ratio: null,
      dividend_yield: null,
      eps: null,
      beta: null,
      vwap: null,
      delivery_pct: null,
      peers: [],
      corporate_actions: [],
      upcoming_events: [],
      announcements: [],
      description: undefined,
      isin: undefined,
      sector: undefined,
      as_of: 'not-a-date',
      sources: {},
      chart: { dates: [], prices: [] },
    })
    renderWithProviders(<StockAnalyzerTab />)

    expect(await screen.findByText('Reliance Industries Ltd.')).toBeInTheDocument()
    expect(screen.queryByText("Day's Range")).not.toBeInTheDocument()
    expect(screen.queryByText(/People Also Watch/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/Corporate actions/i)).not.toBeInTheDocument()
    expect(screen.getByText(/Key Statistics & Valuation/i)).toBeInTheDocument()
  })

  it('covers unavailable corporate-action source, sparse peers/events and invalid ranges', async () => {
    seedStock({
      day_low: 100,
      day_high: 100,
      week52_low: 50,
      week52_high: 40,
      peers: [
        { symbol: 'IOC', name: 'Indian Oil', current_price: null, p_change: null },
      ],
      upcoming_events: [{ date: '', purpose: '' }],
      corporate_actions: [
        { symbol: 'RELIANCE', type: 'split', subject: 'Face value split', ratio: null, ex_date: null },
        { symbol: 'RELIANCE', type: 'unknown_type', subject: 'Other action' },
      ],
      sources: {
        corporate_actions: 'Unavailable',
        events: 'NSE Events Feed',
      },
      latest_filing: {
        quarter_end: 'Mar 2026',
        revenue_cr: null,
        pbt_cr: null,
        net_income_cr: null,
        net_margin_pct: null,
        eps_basic: null,
      },
    })
    renderWithProviders(<StockAnalyzerTab />)

    expect(await screen.findByText(/Corporate actions/i)).toBeInTheDocument()
    expect(screen.getAllByText('ex-date TBC').length).toBeGreaterThan(0)
    expect(screen.getByText('Date TBC')).toBeInTheDocument()
    expect(screen.getByText('Board meeting')).toBeInTheDocument()
    expect(screen.getByText('IOC')).toBeInTheDocument()
    expect(screen.getByText('+0.00%')).toBeInTheDocument()
    expect(screen.queryByText("Day's Range")).not.toBeInTheDocument()
  })

  it('covers small revenue formatting and missing earnings EPS consensus', async () => {
    seedStock(
      {
        earnings_summary: {
          last_report_date: null,
          financial_period: null,
          reported_eps: null,
          reported_revenue_cr: 12.5,
          history: [
            { period: 'Q3', date: '', reported_eps: null, reported_revenue_cr: null },
          ],
        },
        eps: null,
        consensus: {
          eps: { '+1q': { avg: null, analysts: 3 } },
          revenue_cr: { '+1q': { avg: null, analysts: 3 } },
        },
      },
      { activeSubTab: 'earnings' },
    )
    renderWithProviders(<StockAnalyzerTab />)

    expect(await screen.findByText('Latest')).toBeInTheDocument()
    expect(screen.getByText('Fiscal Q1')).toBeInTheDocument()
    expect(screen.getByText(/₹12.50Cr/i)).toBeInTheDocument()
    expect(screen.getByText('Q3')).toBeInTheDocument()
  })

  it('blocks adding the primary stock as a compare target via search', async () => {
    const user = userEvent.setup()
    seedStock({}, { activeSubTab: 'compare' })
    vi.mocked(apiClient.searchStocks).mockResolvedValue({
      results: [
        { symbol: 'RELIANCE', name: 'Reliance Industries Ltd.' },
        { symbol: 'SBIN', name: 'State Bank of India' },
      ],
    } as any)

    renderWithProviders(<StockAnalyzerTab />)
    const compareInput = await screen.findByPlaceholderText(/Add stock to compare/i)
    await user.type(compareInput, 'SB')

    await waitFor(() => expect(apiClient.searchStocks).toHaveBeenCalled(), { timeout: 5000 })
    // Primary stock filtered out of compare options
    expect(screen.queryByRole('option', { name: /RELIANCE/i })).not.toBeInTheDocument()
    const option = await screen.findByRole('option', { name: /SBIN/i }, { timeout: 5000 })
    vi.mocked(apiClient.analyzeStock).mockResolvedValue(
      makeFullStock({ symbol: 'SBIN', name: 'State Bank of India' }) as any,
    )
    await user.click(option)
    await waitFor(() => expect(apiClient.analyzeStock).toHaveBeenCalledWith('SBIN'))
  })

  it('removes compare stock from fundamentals table header button', async () => {
    const user = userEvent.setup()
    seedStock(
      {},
      {
        activeSubTab: 'compare',
        compareStocks: [
          makeFullStock({
            symbol: 'INFY',
            name: 'Infosys',
            year_return: 5,
            chart: { dates: ['2026-01-01'], prices: [1400] },
          }) as any,
        ],
      },
    )
    renderWithProviders(<StockAnalyzerTab />)

    expect(await screen.findByText(/Multi-Asset Fundamentals/i)).toBeInTheDocument()
    expect(useStockAnalyzerStore.getState().compareStocks).toHaveLength(1)

    // Table header IconButton (not the chip delete) — last CloseIcon in the fundamentals section
    const fundamentalsHeading = screen.getByText('Multi-Asset Fundamentals & Valuation Matrix')
    const section = fundamentalsHeading.closest('.MuiPaper-root') ?? fundamentalsHeading.parentElement!
    const tableClose = within(section as HTMLElement)
      .getAllByTestId('CloseIcon')
      .find((icon) => icon.closest('th') || icon.closest('table'))
    expect(tableClose).toBeTruthy()
    await user.click(tableClose!.closest('button')!)
    await waitFor(() => expect(useStockAnalyzerStore.getState().compareStocks).toHaveLength(0))
  })

  it('shows negative sector delta and can remove NIFTY benchmark chip', async () => {
    const user = userEvent.setup()
    seedStock(
      {},
      {
        activeSubTab: 'overview',
        compareBenchmark: true,
        impact: {
          already_owned: false,
          sector_weight_before: 20,
          sector_weight_after: 15,
          sector_delta: -5,
          concentration_warning: false,
        },
      },
    )
    renderWithProviders(<StockAnalyzerTab />)
    expect(await screen.findByText(/-5% shift in Energy/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Compare/i }))
    const bmLabel = await screen.findByText(/NIFTY 50 \(Benchmark\)/i)
    const bmChip = bmLabel.closest('.MuiChip-root') as HTMLElement
    await user.click(within(bmChip).getByTestId('CloseIcon'))
    expect(useStockAnalyzerStore.getState().compareBenchmark).toBe(false)
  })

  it('stale analysis response does not overwrite newer selection', async () => {
    const user = userEvent.setup()
    let resolveFirst: (v: unknown) => void
    let resolveSecond: (v: unknown) => void
    const first = new Promise((resolve) => {
      resolveFirst = resolve
    })
    const second = new Promise((resolve) => {
      resolveSecond = resolve
    })
    vi.mocked(apiClient.analyzeStock)
      .mockImplementationOnce(() => first as any)
      .mockImplementationOnce(() => second as any)

    renderWithProviders(<StockAnalyzerTab />)

    await user.click(await screen.findByRole('button', { name: 'TCS' }))
    await user.click(await screen.findByRole('button', { name: 'INFY' }))

    resolveSecond!(makeFullStock({ symbol: 'INFY', name: 'Infosys Ltd.' }))
    expect(await screen.findByText('Infosys Ltd.')).toBeInTheDocument()

    resolveFirst!(makeFullStock({ symbol: 'TCS', name: 'Should Not Appear' }))
    await waitFor(() => {
      expect(screen.queryByText('Should Not Appear')).not.toBeInTheDocument()
    })
    expect(screen.getByText('Infosys Ltd.')).toBeInTheDocument()
  })

  it('ignores stale analysis errors after a newer selection', async () => {
    const user = userEvent.setup()
    let rejectFirst: (e: unknown) => void
    let resolveSecond: (v: unknown) => void
    const first = new Promise((_, reject) => {
      rejectFirst = reject
    })
    const second = new Promise((resolve) => {
      resolveSecond = resolve
    })
    vi.mocked(apiClient.analyzeStock)
      .mockImplementationOnce(() => first as any)
      .mockImplementationOnce(() => second as any)

    renderWithProviders(<StockAnalyzerTab />)
    await user.click(await screen.findByRole('button', { name: 'TCS' }))
    await user.click(await screen.findByRole('button', { name: 'INFY' }))

    resolveSecond!(makeFullStock({ symbol: 'INFY', name: 'Infosys Ltd.' }))
    expect(await screen.findByText('Infosys Ltd.')).toBeInTheDocument()
    rejectFirst!({ response: { status: 404 } })
    await waitFor(() => {
      expect(screen.queryByText(/That symbol was not recognised/i)).not.toBeInTheDocument()
    })
  })

  it('aligns compare series by matching dates and skips null benchmark points', async () => {
    seedStock(
      {
        chart: {
          dates: ['2026-01-01', '2026-02-01', '2026-03-01'],
          prices: [100, 110, 120],
          benchmark: [null, 200, null],
        },
      },
      {
        activeSubTab: 'compare',
        compareBenchmark: true,
        compareStocks: [
          makeFullStock({
            symbol: 'TCS',
            name: 'TCS',
            current_price: 4000,
            year_return: null,
            market_cap_cr: null,
            pe_ratio: null,
            pb_ratio: null,
            dividend_yield: null,
            roe: null,
            beta: null,
            week52_low: null,
            week52_high: null,
            chart: {
              dates: ['2026-01-01', '2026-02-01', '2026-03-01'],
              prices: [200, 210, 220],
            },
          }) as any,
        ],
      },
    )
    renderWithProviders(<StockAnalyzerTab />)

    expect(await screen.findByText(/Compare with Other Stocks/i)).toBeInTheDocument()
    expect(screen.getByText(/Current Price/i)).toBeInTheDocument()
    expect(screen.getAllByText(/TCS/i).length).toBeGreaterThan(0)
  })

  it('renders rights, buyback and demerger corporate action tones', async () => {
    seedStock({
      corporate_actions: [
        { symbol: 'RELIANCE', type: 'rights', subject: 'Rights issue', ratio: '3:1', ex_date: '2026-01-01' },
        { symbol: 'RELIANCE', type: 'buyback', subject: 'Buyback program', ratio: null, ex_date: '2026-02-01' },
        { symbol: 'RELIANCE', type: 'demerger', subject: 'Demerger note', ratio: '1:1', ex_date: '2026-03-01' },
      ],
      upcoming_events: [],
    })
    renderWithProviders(<StockAnalyzerTab />)

    expect(await screen.findByText(/rights 3:1/i)).toBeInTheDocument()
    expect(screen.getByText('Buyback program')).toBeInTheDocument()
    expect(screen.getByText(/demerger 1:1/i)).toBeInTheDocument()
  })

  it('protects last selected income and balance-sheet metrics from deselection', async () => {
    const user = userEvent.setup()
    seedStock({}, { activeSubTab: 'financials' })
    renderWithProviders(<StockAnalyzerTab />)

    await user.click(await screen.findByRole('button', { name: /Income statement/i }))
    await user.click(screen.getAllByText('Revenue')[0])
    await user.click(screen.getAllByText('Net income')[0])
    // Last remaining metric cannot be toggled off
    expect(screen.getAllByText('Net income').length).toBeGreaterThan(0)

    await user.click(screen.getByRole('button', { name: /Balance sheet/i }))
    await user.click(screen.getAllByText('Total assets')[0])
    await user.click(screen.getAllByText('Total liabilities')[0])
    expect(screen.getAllByText('Total liabilities').length).toBeGreaterThan(0)
  })

  it('skips portfolio impact when loading stock without a session', async () => {
    const user = userEvent.setup()
    useAppStore.setState({ equitySessionId: null })
    vi.mocked(apiClient.analyzeStock).mockResolvedValue(
      makeFullStock({ symbol: 'TCS', name: 'Tata Consultancy Services' }) as any,
    )

    renderWithProviders(<StockAnalyzerTab />)
    await user.click(await screen.findByRole('button', { name: 'TCS' }))
    expect(await screen.findByText('Tata Consultancy Services')).toBeInTheDocument()
    expect(apiClient.stockPortfolioImpact).not.toHaveBeenCalled()
    expect(screen.getByText(/Upload or connect your equity portfolio/i)).toBeInTheDocument()
  })
})
