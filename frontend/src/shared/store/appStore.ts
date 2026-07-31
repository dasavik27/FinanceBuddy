import api from '../api/client'
import authClient from '../auth/authClient'
import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
/**
 * Persisted state is plain localStorage.
 *
 * It used to be AES-wrapped with a key hardcoded in this file - obfuscation, not
 * encryption, since the key shipped in the bundle and anyone with the device could
 * undo it in one line. It bought nothing and cost the whole crypto-js library in the
 * first-paint chunk.
 *
 * What actually changed the risk: a PAN is no longer a credential. It identified
 * users, so leaving it readable mattered; it is now profile data, and the thing worth
 * protecting is the access token - which the auth client stores and refreshes itself.
 */

interface Filters {
  benchmark: string
  categories: string[]
  amcs: string[]
  plan: 'All' | 'Direct' | 'Regular'
  minAlloc: number
}

interface AppState {
  pan: string | null

  /** The account id the server issued. Null when signed out. */
  userId: string | null
  email: string | null
  setIdentity: (identity: { userId: string | null; email?: string | null; pan?: string | null }) => void
  clearIdentity: () => void

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
  clearSession: (type?: string) => void
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

      userId: null,
      email: null,
      setIdentity: ({ userId, email, pan }) =>
        set((state) => ({
          userId,
          email: email !== undefined ? email : state.email,
          pan: pan !== undefined ? pan : state.pan,
        })),

      /**
       * Drop local identity without calling the server.
       *
       * Used by the 401 interceptor, where the credential is already invalid - and
       * where calling logout() would recurse through another failing request.
       */
      clearIdentity: () =>
        set({
          userId: null,
          email: null,
          pan: null,
          mfSessionId: null,
          taxSessionId: null,
          parseData: null,
          isPartial: false,
        }),

      taxSlab: 30,
      setTaxSlab: (slab) => set({ taxSlab: slab }),

      taxRegime: 'new',
      setTaxRegime: (regime) => set({ taxRegime: regime }),

      activeModule: 'mutual_funds',
      // No-op when unchanged. Each domain dashboard calls this from a mount effect, so
      // it fired on every navigation and every remount — and any set() produces a new
      // state object, waking every subscriber even though nothing changed.
      setActiveModule: (module) =>
        set((s) => (s.activeModule === module ? s : { activeModule: module })),

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

      // `type` is optional: omitted (or an unrecognized module such as
      // 'indian_stocks', which owns no session id) clears BOTH. The previous version
      // only branched on the two known modules, so signing out while the stocks module
      // was active silently cleared neither session — the same class of no-op as
      // passing a MouseEvent in here, just narrower.
      clearSession: (type) =>
        set((state) => {
          const clearsMf = !type || type === 'mutual_funds' || type === 'indian_stocks'
          const clearsTax = !type || type === 'tax_expert' || type === 'indian_stocks'
          return {
            mfSessionId: clearsMf ? null : state.mfSessionId,
            taxSessionId: clearsTax ? null : state.taxSessionId,
            parseData: null,
            isPartial: false,
            lastSynced: Date.now(),
          }
        }),
        
      logout: () => {
        try {
          // Body intentionally empty: the server takes the account from the request
          // identity. It used to read the PAN from here, which made logout an
          // unauthenticated way to destroy any named user's sessions.
          if (get().userId || get().pan) {
            api.post('/auth/logout').catch(console.error)
          }
          // Ends the provider session too, so the next visit does not silently
          // resume via a still-valid refresh token.
          void authClient.signOut()
          // Only our own key. localStorage.clear() also wiped the auth client's
          // session and anything else on the origin.
          localStorage.removeItem('finance-buddy-storage')
          sessionStorage.clear()
        } catch (e) {
          console.error(e)
        }
        set({
          userId: null,
          email: null,
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
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        // Not the access token - the auth client owns that, including refresh.
        userId: state.userId,
        email: state.email,
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
export const useUserId = () => useAppStore((s) => s.userId)
/** Signed in either way - provider token or the legacy PAN. */
export const useIsAuthenticated = () => useAppStore((s) => Boolean(s.userId || s.pan))
export const useLogout = () => useAppStore(s => s.logout)
export const useTaxSlab = () => useAppStore(s => s.taxSlab)
export const useSetTaxSlab = () => useAppStore(s => s.setTaxSlab)
export const useTaxRegime = () => useAppStore(s => s.taxRegime)
export const useSetTaxRegime = () => useAppStore(s => s.setTaxRegime)
