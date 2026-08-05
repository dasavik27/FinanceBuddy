import { describe, it, expect, beforeEach } from 'vitest'
import { useStockAnalyzerStore } from './useStockAnalyzerStore'
import type { StockAnalysis, StockSearchResult } from '../types'

describe('useStockAnalyzerStore', () => {
  beforeEach(() => {
    localStorage.clear()
    useStockAnalyzerStore.getState().clear()
  })

  it('initializes with default state', () => {
    const state = useStockAnalyzerStore.getState()
    expect(state.query).toBe('')
    expect(state.stock).toBeNull()
    expect(state.activeSubTab).toBe('overview')
    expect(state.activeTimeframe).toBe('1Y')
    expect(state.chartType).toBe('area')
    expect(state.compareBenchmark).toBe(true)
    expect(state.watchlist).toEqual(['RELIANCE', 'TCS', 'HDFCBANK', 'INFY'])
  })

  it('updates query, selectedStock, and stock', () => {
    const stockResult: StockSearchResult = {
      symbol: 'INFY',
      name: 'Infosys Ltd',
      exchange: 'NSE',
    }
    const mockStock: StockAnalysis = {
      symbol: 'INFY',
      name: 'Infosys Ltd',
      cmp: 1500,
      change: 15,
      change_pct: 1.0,
      technical_signals: {} as any,
      fundamentals: {} as any,
    } as any

    useStockAnalyzerStore.getState().setQuery('INFY')
    expect(useStockAnalyzerStore.getState().query).toBe('INFY')

    useStockAnalyzerStore.getState().setSelectedStock(stockResult)
    expect(useStockAnalyzerStore.getState().selectedStock).toEqual(stockResult)

    useStockAnalyzerStore.getState().setStock(mockStock)
    expect(useStockAnalyzerStore.getState().stock).toEqual(mockStock)
  })

  it('handles comparison stocks limit and removal', () => {
    const createStock = (sym: string): StockAnalysis => ({
      symbol: sym,
      name: `${sym} Ltd`,
      cmp: 1000,
    } as any)

    const s1 = createStock('INFY')
    const s2 = createStock('TCS')
    const s3 = createStock('WIPRO')
    const s4 = createStock('HCLTECH')
    const s5 = createStock('TECHM')

    useStockAnalyzerStore.getState().addCompareStock(s1)
    useStockAnalyzerStore.getState().addCompareStock(s2)
    useStockAnalyzerStore.getState().addCompareStock(s3)
    useStockAnalyzerStore.getState().addCompareStock(s4)
    expect(useStockAnalyzerStore.getState().compareStocks).toHaveLength(4)

    // Adding duplicate does nothing
    useStockAnalyzerStore.getState().addCompareStock(s1)
    expect(useStockAnalyzerStore.getState().compareStocks).toHaveLength(4)

    // Adding 5th replaces first
    useStockAnalyzerStore.getState().addCompareStock(s5)
    expect(useStockAnalyzerStore.getState().compareStocks).toHaveLength(4)
    expect(useStockAnalyzerStore.getState().compareStocks.map(s => s.symbol)).toEqual(['TCS', 'WIPRO', 'HCLTECH', 'TECHM'])

    // Remove stock
    useStockAnalyzerStore.getState().removeCompareStock('TCS')
    expect(useStockAnalyzerStore.getState().compareStocks.map(s => s.symbol)).toEqual(['WIPRO', 'HCLTECH', 'TECHM'])

    // Clear compare stocks
    useStockAnalyzerStore.getState().clearCompareStocks()
    expect(useStockAnalyzerStore.getState().compareStocks).toEqual([])
  })

  it('toggles watchlist items and saves to localStorage', () => {
    useStockAnalyzerStore.getState().toggleWatchlist('RELIANCE') // Already exists -> remove
    expect(useStockAnalyzerStore.getState().watchlist).not.toContain('RELIANCE')

    useStockAnalyzerStore.getState().toggleWatchlist('TATAMOTORS') // New -> add
    expect(useStockAnalyzerStore.getState().watchlist).toContain('TATAMOTORS')
  })
})
