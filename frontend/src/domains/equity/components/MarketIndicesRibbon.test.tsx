import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/utils'
import { MarketIndicesRibbon } from './MarketIndicesRibbon'
import { apiClient } from '../../../shared/api/client'
import { useStockAnalyzerStore } from '../hooks/useStockAnalyzerStore'

vi.mock('../../../shared/api/client', () => ({
  apiClient: {
    getMarketIndices: vi.fn(),
  },
}))

describe('MarketIndicesRibbon', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useStockAnalyzerStore.getState().clear()
  })

  it('fetches and displays market indices and watchlist buttons', async () => {
    vi.mocked(apiClient.getMarketIndices).mockResolvedValue({
      indices: [
        { symbol: 'NIFTY 50', name: 'NIFTY 50', price: 24500, change: 120, p_change: 0.5 },
        { symbol: 'SENSEX', name: 'BSE SENSEX', price: 80000, change: 300, p_change: 0.4 },
      ],
    } as any)

    const onSelectStock = vi.fn()
    renderWithProviders(<MarketIndicesRibbon onSelectStock={onSelectStock} />)

    expect(await screen.findByText('NIFTY 50')).toBeInTheDocument()
    expect(screen.getByText('SENSEX')).toBeInTheDocument()
    expect(screen.getByText('24,500.00')).toBeInTheDocument()
    expect(screen.getByText('+0.50%')).toBeInTheDocument()

    // Watchlist item click
    const relianceBtn = screen.getByRole('button', { name: 'RELIANCE' })
    await userEvent.click(relianceBtn)
    expect(onSelectStock).toHaveBeenCalledWith({ symbol: 'RELIANCE', name: 'RELIANCE' })
  })

  it('uses fallback indices on API error', async () => {
    vi.mocked(apiClient.getMarketIndices).mockRejectedValue(new Error('Network error'))

    renderWithProviders(<MarketIndicesRibbon onSelectStock={vi.fn()} />)

    expect(await screen.findByText('NIFTY 50')).toBeInTheDocument()
    expect(screen.getByText('24,835.80')).toBeInTheDocument()
    expect(screen.getByText('SENSEX')).toBeInTheDocument()
    expect(screen.getByText('81,455.40')).toBeInTheDocument()
  })
})
