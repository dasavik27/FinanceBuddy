import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface Filters {
  benchmark: string
  categories: string[]
  amcs: string[]
  plan: 'All' | 'Direct' | 'Regular'
  minAlloc: number
}

interface AppState {
  pan: string | null
  setPan: (pan: string | null) => void

  taxSlab: number
  setTaxSlab: (slab: number) => void

  taxRegime: 'new' | 'old'
  setTaxRegime: (regime: 'new' | 'old') => void

  activeModule: 'mutual_funds' | 'indian_stocks' | 'tax_expert'
  setActiveModule: (module: 'mutual_funds' | 'indian_stocks' | 'tax_expert') => void

  mfSessionId: string | null
  stocksSessionId: string | null
  taxSessionId: string | null
  
  parseData: any | null
  filters: Filters
  isPartial: boolean

  lastSynced: number
  setSession: (id: string, type: string, data: any) => void
  setSessionById: (id: string, type: string) => void
  clearSession: (type: string) => void
  setFilters: (f: Partial<Filters>) => void
  triggerRefresh: () => void
  logout: () => void
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      pan: null,
      setPan: (pan) => set({ pan }),

      taxSlab: 30,
      setTaxSlab: (slab) => set({ taxSlab: slab }),

      taxRegime: 'new',
      setTaxRegime: (regime) => set({ taxRegime: regime }),

      activeModule: 'mutual_funds',
      setActiveModule: (module) => set({ activeModule: module }),

      mfSessionId: null,
      stocksSessionId: null,
      taxSessionId: null,

      parseData: null,
      isPartial: false,
      lastSynced: Date.now(),
      filters: {
        benchmark: 'Nifty 50',
        categories: [],
        amcs: [],
        plan: 'All',
        minAlloc: 0,
      },

      setSession: (id, type, data) =>
        set((state) => ({
          mfSessionId: type === 'mutual_funds' ? id : state.mfSessionId,
          stocksSessionId: type === 'indian_stocks' ? id : state.stocksSessionId,
          taxSessionId: type === 'tax_expert' ? id : state.taxSessionId,
          parseData: data,
          isPartial: data?.is_partial ?? false,
          lastSynced: Date.now(),
          filters: {
            benchmark: 'Nifty 50',
            categories: data?.categories ?? [],
            amcs: data?.amcs ?? [],
            plan: 'All',
            minAlloc: 0,
          },
        })),

      setSessionById: (id, type) =>
        set((state) => ({
          mfSessionId: type === 'mutual_funds' ? id : state.mfSessionId,
          stocksSessionId: type === 'indian_stocks' ? id : state.stocksSessionId,
          taxSessionId: type === 'tax_expert' ? id : state.taxSessionId,
          lastSynced: Date.now(),
          filters: { benchmark: 'Nifty 50', categories: [], amcs: [], plan: 'All', minAlloc: 0 },
        })),

      clearSession: (type) =>
        set((state) => ({ 
          mfSessionId: type === 'mutual_funds' ? null : state.mfSessionId,
          stocksSessionId: type === 'indian_stocks' ? null : state.stocksSessionId,
          taxSessionId: type === 'tax_expert' ? null : state.taxSessionId,
          parseData: null, 
          isPartial: false, 
          lastSynced: Date.now() 
        })),

      logout: () => set({ pan: null, mfSessionId: null, stocksSessionId: null, taxSessionId: null, parseData: null, isPartial: false }),

      setFilters: (f) =>
        set((s) => ({ filters: { ...s.filters, ...f } })),

      triggerRefresh: () => set((state) => ({ lastSynced: Date.now() }))
    }),
    {
      name: 'finance-buddy-storage',
      partialize: (state) => ({ pan: state.pan, taxRegime: state.taxRegime, taxSessionId: state.taxSessionId })
    }
  )
)

// Selector helpers
export const useSessionId = () => useAppStore((s) => {
  if (s.activeModule === 'mutual_funds') return s.mfSessionId
  if (s.activeModule === 'indian_stocks') return s.stocksSessionId
  if (s.activeModule === 'tax_expert') return s.taxSessionId
  return null
})
export const useMfSessionId = () => useAppStore((s) => s.mfSessionId)
export const useStocksSessionId = () => useAppStore((s) => s.stocksSessionId)
export const useTaxSessionId = () => useAppStore((s) => s.taxSessionId)
export const useFilters = () => useAppStore((s) => s.filters)
export const useParseData = () => useAppStore((s) => s.parseData)
export const useIsPartial = () => useAppStore((s) => s.isPartial)
export const useLastSynced = () => useAppStore((s) => s.lastSynced)
export const useRefreshTrigger = () => useAppStore((s) => s.triggerRefresh)
export const usePan = () => useAppStore((s) => s.pan)
export const useLogout = () => useAppStore(s => s.logout)
export const useTaxSlab = () => useAppStore(s => s.taxSlab)
export const useSetTaxSlab = () => useAppStore(s => s.setTaxSlab)
export const useTaxRegime = () => useAppStore(s => s.taxRegime)
export const useSetTaxRegime = () => useAppStore(s => s.setTaxRegime)
