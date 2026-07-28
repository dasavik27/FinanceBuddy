import api from '../api/client'
import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import CryptoJS from 'crypto-js'

const SECRET_KEY = 'FINANCE_BUDDY_SECURE_STORAGE_KEY_2026'

const encryptedStorage = {
  getItem: (name: string): string | null => {
    const encrypted = localStorage.getItem(name)
    if (!encrypted) return null
    try {
      const decrypted = CryptoJS.AES.decrypt(encrypted, SECRET_KEY).toString(CryptoJS.enc.Utf8)
      return decrypted || null
    } catch {
      return null
    }
  },
  setItem: (name: string, value: string): void => {
    const encrypted = CryptoJS.AES.encrypt(value, SECRET_KEY).toString()
    localStorage.setItem(name, encrypted)
  },
  removeItem: (name: string): void => {
    localStorage.removeItem(name)
  }
}


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
  taxSessionId: string | null
  
  parseData: any | null
  filters: Filters
  isPartial: boolean

  lastSynced: number
  setSession: (id: string, type: string, data: any) => void
  setSessionById: (id: string, type: string) => void
  clearSession: (type: string) => void
  clearAllSessionsByPan: (pan: string) => void
  setFilters: (f: Partial<Filters>) => void
  triggerRefresh: () => void
  logout: () => void

  compareFunds: Record<string, string[]>
  setCompareFunds: (sid: string, funds: string[]) => void
  compareBench: Record<string, string>
  setCompareBench: (sid: string, bench: string) => void
}

export const useAppStore = create<AppState>()(
  persist(
    (set, get) => ({
      pan: null,
      setPan: (pan) => set({ pan }),

      taxSlab: 30,
      setTaxSlab: (slab) => set({ taxSlab: slab }),

      taxRegime: 'new',
      setTaxRegime: (regime) => set({ taxRegime: regime }),

      activeModule: 'mutual_funds',
      setActiveModule: (module) => set({ activeModule: module }),

      mfSessionId: null,
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

      compareFunds: {},
      setCompareFunds: (sid, funds) => set((s) => ({ compareFunds: { ...s.compareFunds, [sid]: funds } })),
      compareBench: {},
      setCompareBench: (sid, bench) => set((s) => ({ compareBench: { ...s.compareBench, [sid]: bench } })),


      setSession: (id, type, data) =>
        set((state) => ({
          mfSessionId: type === 'mutual_funds' ? id : state.mfSessionId,
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
          taxSessionId: type === 'tax_expert' ? id : state.taxSessionId,
          lastSynced: Date.now(),
          filters: { benchmark: 'Nifty 50', categories: [], amcs: [], plan: 'All', minAlloc: 0 },
        })),

      clearSession: (type) =>
        set((state) => ({
          mfSessionId: type === 'mutual_funds' ? null : state.mfSessionId,
          taxSessionId: type === 'tax_expert' ? null : state.taxSessionId,
          parseData: null, 
          isPartial: false, 
          lastSynced: Date.now() 
        })),
        
      clearAllSessionsByPan: (panToClear: string) => {
        const state = get()
        if (state.pan?.toUpperCase() === panToClear.toUpperCase()) {
            set({
                pan: null,
                mfSessionId: null,
                taxSessionId: null,
                parseData: null,
                isPartial: false,
                lastSynced: Date.now()
            })
        }
      },

      logout: () => {
        try {
          const pan = get().pan;
          if (pan) {
            api.post('/auth/logout', { pan }).catch(console.error);
          }
          localStorage.clear()
          sessionStorage.clear()
        } catch (e) {
          console.error(e)
        }
        set({
          pan: null,
          mfSessionId: null,
          taxSessionId: null,
          parseData: null,
          isPartial: false,
          taxRegime: 'new',
          filters: { benchmark: 'Nifty 50', categories: [], amcs: [], plan: 'All', minAlloc: 0 },
          lastSynced: Date.now(),
          compareFunds: {},
          compareBench: {}
        })
      },

      setFilters: (f) =>
        set((s) => ({ filters: { ...s.filters, ...f } })),

      triggerRefresh: () => set((state) => ({ lastSynced: Date.now() }))
    }),
    {
      name: 'finance-buddy-storage',
      storage: createJSONStorage(() => encryptedStorage),
      partialize: (state) => ({ 
        pan: state.pan, 
        taxRegime: state.taxRegime, 
        taxSessionId: state.taxSessionId,
        compareFunds: state.compareFunds,
        compareBench: state.compareBench
      })
    }
  )
)

// Selector helpers
export const useSessionId = () => useAppStore((s) => {
  if (s.activeModule === 'mutual_funds') return s.mfSessionId
  if (s.activeModule === 'tax_expert') return s.taxSessionId
  return null
})
export const useMfSessionId = () => useAppStore((s) => s.mfSessionId)
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
export const useClearAllSessionsByPan = () => useAppStore(s => s.clearAllSessionsByPan)
