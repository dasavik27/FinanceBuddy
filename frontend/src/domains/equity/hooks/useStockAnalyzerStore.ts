import { create } from 'zustand'
import type { StockAnalysis, StockSearchResult } from '../types'

export type GoogleFinanceSubTab = 'overview' | 'indicators' | 'compare' | 'financials' | 'earnings'
export type ChartTimeframe = '1D' | '5D' | '1M' | '6M' | 'YTD' | '1Y' | '5Y'
export type ChartDisplayType = 'area' | 'line' | 'candlestick'

interface StockAnalyzerState {
  query: string
  selectedStock: StockSearchResult | null
  stock: StockAnalysis | null
  impactAmount: string
  impact: any | null
  analysisError: string | null
  activeSubTab: GoogleFinanceSubTab
  activeTimeframe: ChartTimeframe
  chartType: ChartDisplayType
  compareBenchmark: boolean
  compareStocks: StockAnalysis[]
  watchlist: string[]
  setQuery: (query: string) => void
  setSelectedStock: (stock: StockSearchResult | null) => void
  setStock: (stock: StockAnalysis | null) => void
  setImpactAmount: (amount: string) => void
  setImpact: (impact: any | null) => void
  setAnalysisError: (error: string | null) => void
  setActiveSubTab: (tab: GoogleFinanceSubTab) => void
  setActiveTimeframe: (tf: ChartTimeframe) => void
  setChartType: (type: ChartDisplayType) => void
  setCompareBenchmark: (enabled: boolean) => void
  addCompareStock: (stock: StockAnalysis) => void
  removeCompareStock: (symbol: string) => void
  clearCompareStocks: () => void
  toggleWatchlist: (symbol: string) => void
  clear: () => void
}

const getInitialWatchlist = (): string[] => {
  try {
    const saved = localStorage.getItem('equity_watchlist_v1')
    return saved ? JSON.parse(saved) : ['RELIANCE', 'TCS', 'HDFCBANK', 'INFY']
  } catch {
    return ['RELIANCE', 'TCS', 'HDFCBANK', 'INFY']
  }
}

/**
 * In-memory store for the Stock Analyzer tab.
 *
 * Keeps the analyzed stock, simulated impact, search query, active sub-tab,
 * timeframe, comparison stocks, and user watchlist across tab switches.
 */
export const useStockAnalyzerStore = create<StockAnalyzerState>((set, get) => ({
  query: '',
  selectedStock: null,
  stock: null,
  impactAmount: '100000',
  impact: null,
  analysisError: null,
  activeSubTab: 'overview',
  activeTimeframe: '1Y',
  chartType: 'area',
  compareBenchmark: true,
  compareStocks: [],
  watchlist: getInitialWatchlist(),

  setQuery: (query: string) => set({ query }),
  setSelectedStock: (selectedStock: StockSearchResult | null) => set({ selectedStock }),
  setStock: (stock: StockAnalysis | null) => set({ stock }),
  setImpactAmount: (impactAmount: string) => set({ impactAmount }),
  setImpact: (impact: any | null) => set({ impact }),
  setAnalysisError: (analysisError: string | null) => set({ analysisError }),
  setActiveSubTab: (activeSubTab: GoogleFinanceSubTab) => set({ activeSubTab }),
  setActiveTimeframe: (activeTimeframe: ChartTimeframe) => set({ activeTimeframe }),
  setChartType: (chartType: ChartDisplayType) => set({ chartType }),
  setCompareBenchmark: (compareBenchmark: boolean) => set({ compareBenchmark }),

  addCompareStock: (stockToCompare: StockAnalysis) => {
    const current = get().compareStocks
    if (current.some((s) => s.symbol.toUpperCase() === stockToCompare.symbol.toUpperCase())) {
      return
    }
    // Limit to max 4 comparison stocks
    if (current.length >= 4) {
      set({ compareStocks: [...current.slice(1), stockToCompare] })
    } else {
      set({ compareStocks: [...current, stockToCompare] })
    }
  },

  removeCompareStock: (symbol: string) => {
    const sym = symbol.toUpperCase()
    set({
      compareStocks: get().compareStocks.filter((s) => s.symbol.toUpperCase() !== sym),
    })
  },

  clearCompareStocks: () => set({ compareStocks: [] }),

  toggleWatchlist: (symbol: string) => {
    const sym = symbol.toUpperCase().trim()
    const current = get().watchlist
    const exists = current.includes(sym)
    const updated = exists ? current.filter((s: string) => s !== sym) : [...current, sym]
    try {
      localStorage.setItem('equity_watchlist_v1', JSON.stringify(updated))
    } catch {
      // Ignore storage errors
    }
    set({ watchlist: updated })
  },

  clear: () =>
    set({
      query: '',
      selectedStock: null,
      stock: null,
      impact: null,
      analysisError: null,
      activeSubTab: 'overview',
      activeTimeframe: '1Y',
      compareStocks: [],
    }),
}))
