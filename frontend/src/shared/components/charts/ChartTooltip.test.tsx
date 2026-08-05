import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../../../test/utils'
import { ChartTooltip } from './ChartTooltip'

describe('ChartTooltip', () => {
  it('returns null when active is false or payload is empty', () => {
    const { container: c1 } = renderWithProviders(<ChartTooltip active={false} payload={[{ name: 'Series', value: 100 }]} />)
    expect(c1.firstChild).toBeNull()

    const { container: c2 } = renderWithProviders(<ChartTooltip active={true} payload={[]} />)
    expect(c2.firstChild).toBeNull()
  })

  it('renders label and currency amounts by default', () => {
    renderWithProviders(
      <ChartTooltip
        active={true}
        label="Jan 2026"
        payload={[
          { name: 'Portfolio Value', value: 500000, color: '#4EDE93' },
          { name: 'Invested', value: 350000, color: '#6366F1' },
        ]}
      />
    )

    expect(screen.getByText('Jan 2026')).toBeInTheDocument()
    expect(screen.getByText('Portfolio Value:')).toBeInTheDocument()
    expect(screen.getByText('₹5,00,000')).toBeInTheDocument()
    expect(screen.getByText('Invested:')).toBeInTheDocument()
    expect(screen.getByText('₹3,50,000')).toBeInTheDocument()
  })

  it('renders percentage formatting when isPct is true', () => {
    renderWithProviders(
      <ChartTooltip
        active={true}
        label="Nifty 50 Comparison"
        isPct={true}
        payload={[{ name: 'CAGR', value: 14.5, color: '#4EDE93' }]}
      />
    )

    expect(screen.getByText('Nifty 50 Comparison')).toBeInTheDocument()
    expect(screen.getByText('+14.50%')).toBeInTheDocument()
  })
})
