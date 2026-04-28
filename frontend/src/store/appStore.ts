import { create } from 'zustand'

interface Filters {
  benchmark:  string
  categories: string[]
  amcs:       string[]
  plan:       'All' | 'Direct' | 'Regular'
  minAlloc:   number
}

interface AppState {
  sessionId:   string | null
  parseData:   any | null
  filters:     Filters
  isPartial:   boolean

  setSession:  (id: string, data: any) => void
  clearSession:() => void
  setFilters:  (f: Partial<Filters>) => void
}

export const useAppStore = create<AppState>((set) => ({
  sessionId:   null,
  parseData:   null,
  isPartial:   false,
  filters: {
    benchmark:  'Nifty 50',
    categories: [],
    amcs:       [],
    plan:       'All',
    minAlloc:   0,
  },

  setSession: (id, data) =>
    set({
      sessionId: id,
      parseData: data,
      isPartial: data?.is_partial ?? false,
      filters: {
        benchmark:  'Nifty 50',
        categories: data?.categories ?? [],
        amcs:       data?.amcs ?? [],
        plan:       'All',
        minAlloc:   0,
      },
    }),

  clearSession: () =>
    set({ sessionId: null, parseData: null, isPartial: false }),

  setFilters: (f) =>
    set((s) => ({ filters: { ...s.filters, ...f } })),
}))

// Selector helpers
export const useSessionId  = () => useAppStore((s) => s.sessionId)
export const useFilters    = () => useAppStore((s) => s.filters)
export const useParseData  = () => useAppStore((s) => s.parseData)
export const useIsPartial  = () => useAppStore((s) => s.isPartial)
