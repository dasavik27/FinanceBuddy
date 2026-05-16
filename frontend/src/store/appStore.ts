import { create } from 'zustand'

interface Filters {
  benchmark: string
  categories: string[]
  amcs: string[]
  plan: 'All' | 'Direct' | 'Regular'
  minAlloc: number
}

interface AppState {
  sessionId: string | null
  parseData: any | null
  filters: Filters
  isPartial: boolean

  lastSynced: number
  setSession: (id: string, data: any) => void
  clearSession: () => void
  setFilters: (f: Partial<Filters>) => void
  triggerRefresh: () => void
}

export const useAppStore = create<AppState>((set) => ({
  sessionId: null,
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

  setSession: (id, data) =>
    set({
      sessionId: id,
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
    }),

  clearSession: () =>
    set({ sessionId: null, parseData: null, isPartial: false, lastSynced: Date.now() }),

  setFilters: (f) =>
    set((s) => ({ filters: { ...s.filters, ...f } })),

  triggerRefresh: () => set({ lastSynced: Date.now() }),
}))

// Selector helpers
export const useSessionId = () => useAppStore((s) => s.sessionId)
export const useFilters = () => useAppStore((s) => s.filters)
export const useParseData = () => useAppStore((s) => s.parseData)
export const useIsPartial = () => useAppStore((s) => s.isPartial)
export const useLastSynced = () => useAppStore((s) => s.lastSynced)
export const useRefreshTrigger = () => useAppStore((s) => s.triggerRefresh)
