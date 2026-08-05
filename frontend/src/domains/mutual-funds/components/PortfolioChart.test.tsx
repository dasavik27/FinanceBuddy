import { describe, it, expect, vi } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/utils'
import PortfolioChart from './PortfolioChart'

describe('PortfolioChart', () => {
  const defaultProps = {
    dates: ['2023-01-01', '2023-02-01', '2023-03-01'],
    portfolioSeries: [100, 110, 125],
    primaryBenchmark: 'Nifty 50',
    primarySeries: [100, 105, 115],
    overlaySeries: {
      'Sensex': [100, 104, 112],
    },
    period: '1Y',
    selectedBenchmarks: ['Nifty 50', 'Sensex'],
    portReturn: 25.0,
    benchReturn: 15.0,
    alpha: 10.0,
    onPeriodChange: vi.fn(),
    onBenchmarksChange: vi.fn(),
  }

  it('renders title, returns, benchmark chips, and period selectors', async () => {
    renderWithProviders(<PortfolioChart {...defaultProps} />)

    expect(screen.getByText('PORTFOLIO PERFORMANCE & ATTRIBUTION')).toBeInTheDocument()
    expect(screen.getByText(/MF \+25\.00%/i)).toBeInTheDocument()
    expect(screen.getByText(/Nifty 50:/i)).toBeInTheDocument()
    expect(screen.getByText(/Sensex:/i)).toBeInTheDocument()

    // Click period selector
    const threeYearBtn = screen.getByText('3Y')
    await userEvent.click(threeYearBtn)
    expect(defaultProps.onPeriodChange).toHaveBeenCalledWith('3Y')

    // Open comparator menu
    const addCompBtn = screen.getByText('+ Add Comparator')
    await userEvent.click(addCompBtn)
    expect(screen.getByText('Nifty Midcap 150')).toBeInTheDocument()
  })
})
