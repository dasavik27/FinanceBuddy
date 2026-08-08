import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/utils'
import PortfolioChart from './PortfolioChart'

vi.mock('recharts', () => {
  const { createElement, useEffect, isValidElement } = require('react')

  const Passthrough = ({ children, onMouseMove, onMouseLeave }: any) =>
    createElement(
      'div',
      {
        'data-testid': 'composed-chart',
        onMouseMove: (ev: any) => {
          // Allow tests to force the empty-payload early-return via data attribute
          if (ev?.currentTarget?.getAttribute?.('data-empty-move') === '1') {
            onMouseMove?.({})
            return
          }
          onMouseMove?.({
            activePayload: [
              {
                payload: {
                  date: '2023-02-01',
                  PortfolioK: 1100,
                  'Nifty 50': 1050,
                  Sensex: 1040,
                },
              },
            ],
          })
        },
        onMouseLeave: () => onMouseLeave?.(),
      },
      children,
    )

  const InvokeAxis = (props: Record<string, unknown>) => {
    useEffect(() => {
      const tick = props.tick as any
      if (isValidElement(tick)) {
        const Tick = tick.type as any
        // January year label (non-short period) + mid-year + short-period day labels
        Tick({ ...tick.props, x: 10, y: 20, payload: { value: '2023-01-15' } })
        Tick({ ...tick.props, x: 10, y: 20, payload: { value: '2023-06-01' } })
        Tick({ ...tick.props, period: '1M', x: 10, y: 20, payload: { value: '2023-03-05' } })
        Tick({ ...tick.props, x: 10, y: 20, payload: { value: '2023-13-01' } }) // invalid month → fallback
        Tick({ ...tick.props, x: 10, y: 20, payload: { value: '' } })
        Tick({ ...tick.props, x: 10, y: 20, payload: null })
      }
      const fmt = props.tickFormatter as ((v: number) => unknown) | undefined
      if (typeof fmt === 'function') fmt(1250)
    }, [])
    return createElement('div', { 'data-testid': 'axis' })
  }

  const InvokeTooltip = (props: Record<string, unknown>) => {
    useEffect(() => {
      const content = props.content as any
      if (isValidElement(content)) {
        const Tip = content.type as any
        // Positive returns + Zerodha ordinal suffixes (1st/2nd/3rd/11th/21st/22nd/23rd)
        ;['2022-11-01', '2022-11-02', '2022-11-03', '2022-11-04', '2022-11-11', '2022-11-21', '2022-11-22', '2022-11-23'].forEach((date) => {
          Tip({
            ...content.props,
            active: true,
            payload: [
              { dataKey: 'PortfolioK', value: 1250, name: 'Portfolio', payload: { date } },
              { dataKey: 'Nifty 50', value: 1150, name: 'Nifty 50', payload: { date } },
            ],
          })
        })
        // Negative portfolio / benchmark pct branches + empty date
        Tip({
          ...content.props,
          active: true,
          payload: [
            { dataKey: 'PortfolioK', value: 800, name: 'Portfolio', payload: { date: '' } },
            { dataKey: 'Nifty 50', value: 700, name: 'Nifty 50', payload: { date: '' } },
          ],
        })
        Tip({
          ...content.props,
          active: true,
          payload: [
            { dataKey: 'PortfolioK', value: 900, name: 'Portfolio', payload: { date: 'bad-date' } },
          ],
        })
        Tip({ ...content.props, active: false, payload: [] })
        Tip({ ...content.props, active: true, payload: null })
        Tip({ ...content.props, active: true, payload: [], basePoint: null })
      }
    }, [])
    return createElement('div', { 'data-testid': 'tooltip' })
  }

  const InvokeBrush = (props: Record<string, unknown>) => {
    useEffect(() => {
      const onChange = props.onChange as ((r: any) => void) | undefined
      const tickFormatter = props.tickFormatter as ((v: string) => unknown) | undefined
      onChange?.({ startIndex: 1, endIndex: 2 })
      onChange?.(null)
      onChange?.({})
      if (typeof tickFormatter === 'function') {
        tickFormatter('2023-01-15')
        tickFormatter('2023-06')
        tickFormatter('raw')
      }
    }, [])
    return createElement('div', { 'data-testid': 'brush' }, props.children as never)
  }

  return {
    ResponsiveContainer: ({ children }: any) => createElement('div', null, children),
    ComposedChart: Passthrough,
    Line: () => createElement('div'),
    Area: () => createElement('div'),
    XAxis: InvokeAxis,
    YAxis: InvokeAxis,
    CartesianGrid: () => createElement('div'),
    Tooltip: InvokeTooltip,
    ReferenceLine: () => createElement('div'),
    Brush: InvokeBrush,
  }
})

describe('PortfolioChart', () => {
  const defaultProps = {
    dates: ['2023-01-01', '2023-02-01', '2023-03-01'],
    portfolioSeries: [100, 110, 125],
    primaryBenchmark: 'Nifty 50',
    primarySeries: [100, 105, 115],
    overlaySeries: {
      Sensex: [100, 104, 112],
    },
    period: '1Y',
    selectedBenchmarks: ['Nifty 50', 'Sensex'],
    portReturn: 25.0,
    benchReturn: 15.0,
    alpha: 10.0,
    onPeriodChange: vi.fn(),
    onBenchmarksChange: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    delete (Element.prototype as any).requestFullscreen
    delete (document as any).exitFullscreen
  })

  it('renders title, returns, benchmark chips, and period selectors', async () => {
    renderWithProviders(<PortfolioChart {...defaultProps} />)

    expect(screen.getByText('PORTFOLIO PERFORMANCE & ATTRIBUTION')).toBeInTheDocument()
    expect(screen.getByText(/MF \+25\.00%/i)).toBeInTheDocument()
    expect(screen.getByText(/Nifty 50:/i)).toBeInTheDocument()
    expect(screen.getByText(/Sensex:/i)).toBeInTheDocument()

    const threeYearBtn = screen.getByText('3Y')
    await userEvent.click(threeYearBtn)
    expect(defaultProps.onPeriodChange).toHaveBeenCalledWith('3Y')

    const addCompBtn = screen.getByText('+ Add Comparator')
    await userEvent.click(addCompBtn)
    expect(screen.getByText('Nifty Midcap 150')).toBeInTheDocument()
  })

  it('toggles benchmarks from the comparator menu and chip delete', async () => {
    const onBenchmarksChange = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(
      <PortfolioChart {...defaultProps} onBenchmarksChange={onBenchmarksChange} />,
    )

    await user.click(screen.getByText('+ Add Comparator'))
    await user.click(screen.getByText('Nifty Midcap 150'))
    expect(onBenchmarksChange).toHaveBeenCalledWith(
      expect.arrayContaining(['Nifty 50', 'Sensex', 'Nifty Midcap 150']),
    )

    const sensexChipDelete = screen.getByText(/Sensex:/i).closest('.MuiChip-root')
      ?.querySelector('[data-testid="CancelIcon"]') as HTMLElement | null
    if (sensexChipDelete) {
      await user.click(sensexChipDelete)
      expect(onBenchmarksChange).toHaveBeenCalledWith(['Nifty 50'])
    }
  })

  it('does not remove the last remaining benchmark', async () => {
    const onBenchmarksChange = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(
      <PortfolioChart
        {...defaultProps}
        selectedBenchmarks={['Nifty 50']}
        overlaySeries={{}}
        onBenchmarksChange={onBenchmarksChange}
      />,
    )

    await user.click(screen.getByText('+ Add Comparator'))
    await user.click(screen.getByRole('menuitem', { name: 'Nifty 50' }))
    expect(onBenchmarksChange).not.toHaveBeenCalled()
  })

  it('caps selected benchmarks at five', async () => {
    const onBenchmarksChange = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(
      <PortfolioChart
        {...defaultProps}
        selectedBenchmarks={['Nifty 50', 'Sensex', 'Nifty Midcap 150', 'Nifty Next 50', 'S&P 500 (US)']}
        overlaySeries={{}}
        onBenchmarksChange={onBenchmarksChange}
      />,
    )

    await user.click(screen.getByText('+ Add Comparator'))
    await user.click(screen.getByRole('menuitem', { name: 'Nifty Smallcap 250' }))
    expect(onBenchmarksChange).not.toHaveBeenCalled()
  })

  it('shows fetching banner when overlays missing for multi-benchmark view', () => {
    renderWithProviders(
      <PortfolioChart
        {...defaultProps}
        overlaySeries={{}}
        selectedBenchmarks={['Nifty 50', 'Sensex']}
      />,
    )
    expect(screen.getByText(/FETCHING LIVE BENCHMARKS/i)).toBeInTheDocument()
  })

  it('covers short-period axis ticks and hover/leave return updates', async () => {
    renderWithProviders(<PortfolioChart {...defaultProps} period="1M" />)

    const chart = screen.getAllByTestId('composed-chart')[0]
    fireEvent.mouseMove(chart)
    await waitFor(() => {
      expect(screen.getByText(/Spot Alpha/i)).toBeInTheDocument()
    })

    fireEvent.mouseLeave(chart)
    await waitFor(() => {
      expect(screen.getByText(/Alpha vs Nifty 50/i)).toBeInTheDocument()
    })
  })

  it('handles empty series gracefully', () => {
    renderWithProviders(
      <PortfolioChart
        {...defaultProps}
        dates={[]}
        portfolioSeries={[]}
        primarySeries={[]}
        overlaySeries={{}}
        selectedBenchmarks={['Nifty 50']}
      />,
    )
    expect(screen.getByText('PORTFOLIO PERFORMANCE & ATTRIBUTION')).toBeInTheDocument()
  })

  it('handles NaN / sparse series values in domain calc', () => {
    renderWithProviders(
      <PortfolioChart
        {...defaultProps}
        portfolioSeries={[NaN, 110, 125]}
        primarySeries={[100, NaN, 115]}
        overlaySeries={{ Sensex: [100] }}
      />,
    )
    expect(screen.getByText(/MF /i)).toBeInTheDocument()
  })

  it('toggles fullscreen mode via Fullscreen API events', async () => {
    const user = userEvent.setup()
    let activeEl: Element | null = null
    Object.defineProperty(document, 'fullscreenElement', {
      configurable: true,
      get: () => activeEl,
    })
    Element.prototype.requestFullscreen = vi.fn(async function (this: Element) {
      activeEl = this
      document.dispatchEvent(new Event('fullscreenchange'))
    }) as any
    document.exitFullscreen = vi.fn(async () => {
      activeEl = null
      document.dispatchEvent(new Event('fullscreenchange'))
    }) as any

    renderWithProviders(<PortfolioChart {...defaultProps} />)
    const buttons = screen.getAllByRole('button')
    const fullscreenBtn = buttons.find((b) => b.querySelector('[data-testid="FullscreenIcon"]'))
    expect(fullscreenBtn).toBeTruthy()
    await user.click(fullscreenBtn!)
    expect(await screen.findByTestId('FullscreenExitIcon')).toBeInTheDocument()

    const exitBtn = screen.getByTestId('FullscreenExitIcon').closest('button')!
    await user.click(exitBtn)
    expect(document.exitFullscreen).toHaveBeenCalled()
  })

  it('shows negative portfolio return styling', () => {
    renderWithProviders(
      <PortfolioChart
        {...defaultProps}
        portfolioSeries={[100, 90, 80]}
        primarySeries={[100, 105, 110]}
      />,
    )
    expect(screen.getByText(/MF -/i)).toBeInTheDocument()
  })

  it('closes comparator menu via onClose and covers January year tick', async () => {
    const user = userEvent.setup()
    renderWithProviders(<PortfolioChart {...defaultProps} period="1Y" dates={['2023-01-01', '2023-06-01', '2024-01-01']} />)

    await user.click(screen.getByText('+ Add Comparator'))
    expect(screen.getByText('Nifty Midcap 150')).toBeInTheDocument()
    await user.keyboard('{Escape}')
    await waitFor(() => {
      expect(screen.queryByRole('menuitem', { name: 'Nifty Midcap 150' })).not.toBeInTheDocument()
    })
  })

  it('uses short overlay series last-value fallback and same-point hover bail', async () => {
    renderWithProviders(
      <PortfolioChart
        {...defaultProps}
        overlaySeries={{ Sensex: [100] }}
        period="3M"
      />,
    )
    const chart = screen.getAllByTestId('composed-chart')[0]
    fireEvent.mouseMove(chart)
    fireEvent.mouseMove(chart)
    await waitFor(() => {
      expect(screen.getByText(/Spot Alpha/i)).toBeInTheDocument()
    })
  })

  it('formats brush ticks for short periods and shows negative alpha chip', () => {
    renderWithProviders(
      <PortfolioChart
        {...defaultProps}
        period="1M"
        portfolioSeries={[100, 95, 90]}
        primarySeries={[100, 110, 120]}
      />,
    )
    expect(screen.getByText(/Alpha vs Nifty 50 -/i)).toBeInTheDocument()
    expect(screen.getByTestId('brush')).toBeInTheDocument()
  })

  it('renders negative benchmark chip returns when series decline', () => {
    renderWithProviders(
      <PortfolioChart
        {...defaultProps}
        portfolioSeries={[100, 110, 120]}
        primarySeries={[100, 90, 80]}
        overlaySeries={{ Sensex: [100, 85, 70] }}
      />,
    )
    expect(screen.getByText(/Sensex: -/i)).toBeInTheDocument()
  })

  it('falls back gradient colors when primary benchmark is not selected', () => {
    renderWithProviders(
      <PortfolioChart
        {...defaultProps}
        primaryBenchmark="Nifty 50"
        selectedBenchmarks={['Sensex']}
        overlaySeries={{ Sensex: [100, 104, 112] }}
      />,
    )
    expect(screen.getByText(/Sensex:/i)).toBeInTheDocument()
    expect(screen.queryByText(/Nifty 50:/i)).not.toBeInTheDocument()
  })

  it('handles null overlaySeries and empty mouse payload without crashing', () => {
    renderWithProviders(
      <PortfolioChart
        {...defaultProps}
        overlaySeries={null as any}
        selectedBenchmarks={['Nifty 50', 'Sensex']}
      />,
    )
    expect(screen.getByText(/FETCHING LIVE BENCHMARKS/i)).toBeInTheDocument()
    const chart = screen.getAllByTestId('composed-chart')[0]
    chart.setAttribute('data-empty-move', '1')
    fireEvent.mouseMove(chart)
    expect(screen.getByText('PORTFOLIO PERFORMANCE & ATTRIBUTION')).toBeInTheDocument()
  })

  it('toggles fullscreen when Fullscreen API is unavailable', async () => {
    const user = userEvent.setup()
    delete (Element.prototype as any).requestFullscreen
    delete (document as any).exitFullscreen
    renderWithProviders(<PortfolioChart {...defaultProps} />)
    const buttons = screen.getAllByRole('button')
    const fullscreenBtn = buttons.find((b) => b.querySelector('[data-testid="FullscreenIcon"]'))
    expect(fullscreenBtn).toBeTruthy()
    await user.click(fullscreenBtn!)
    expect(screen.getByTestId('FullscreenIcon')).toBeInTheDocument()
  })
})
