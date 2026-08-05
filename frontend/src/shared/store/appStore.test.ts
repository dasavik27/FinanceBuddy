import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  useAppStore,
  useSessionId,
  useMfSessionId,
  useTaxSessionId,
  useEquitySessionId,
  useFilters,
  useParseData,
  useIsPartial,
  useLastSynced,
  useRefreshTrigger,
  usePan,
  useUserId,
  useUserRole,
  useUserStatus,
  useIsAuthenticated,
  useLogout,
  useTaxSlab,
  useSetTaxSlab,
  useTaxRegime,
  useSetTaxRegime,
} from './appStore'
import { renderHook, act } from '@testing-library/react'
import api from '../api/client'
import authClient from '../auth/authClient'

vi.mock('../api/client', () => ({
  default: {
    post: vi.fn().mockResolvedValue({ data: {} }),
  },
}))

vi.mock('../auth/authClient', async (importOriginal) => {
  const actual = await importOriginal<any>()
  return {
    ...actual,
    default: {
      ...actual.default,
      signOut: vi.fn().mockResolvedValue(undefined),
    },
  }
})

describe('appStore', () => {
  beforeEach(() => {
    act(() => {
      useAppStore.getState().clearIdentity()
    })
    vi.clearAllMocks()
  })

  it('sets and clears identity', () => {
    act(() => {
      useAppStore.getState().setIdentity({
        userId: 'u-123',
        email: 'test@example.com',
        displayName: 'Test User',
        pan: 'ABCDE1234F',
        status: 'active',
        role: 'user',
      })
    })

    const state = useAppStore.getState()
    expect(state.userId).toBe('u-123')
    expect(state.email).toBe('test@example.com')
    expect(state.displayName).toBe('Test User')
    expect(state.pan).toBe('ABCDE1234F')
    expect(state.status).toBe('active')
    expect(state.role).toBe('user')

    act(() => {
      useAppStore.getState().clearIdentity()
    })

    const cleared = useAppStore.getState()
    expect(cleared.userId).toBeNull()
    expect(cleared.email).toBeNull()
    expect(cleared.pan).toBeNull()
    expect(cleared.status).toBeNull()
    expect(cleared.role).toBeNull()
  })

  it('updates tax slab and regime', () => {
    act(() => {
      useAppStore.getState().setTaxSlab(20)
      useAppStore.getState().setTaxRegime('old')
    })

    expect(useAppStore.getState().taxSlab).toBe(20)
    expect(useAppStore.getState().taxRegime).toBe('old')
  })

  it('sets active module conditionally', () => {
    act(() => {
      useAppStore.getState().setActiveModule('indian_stocks')
    })
    expect(useAppStore.getState().activeModule).toBe('indian_stocks')

    // Setting same module should preserve identity
    const s1 = useAppStore.getState()
    act(() => {
      useAppStore.getState().setActiveModule('indian_stocks')
    })
    const s2 = useAppStore.getState()
    expect(s1).toBe(s2)
  })

  it('handles sessions for mutual funds, tax, and equity', () => {
    act(() => {
      useAppStore.getState().setSession('mf-1', 'mutual_funds', {
        is_partial: true,
        categories: ['Large Cap'],
        amcs: ['HDFC'],
      })
    })

    let state = useAppStore.getState()
    expect(state.mfSessionId).toBe('mf-1')
    expect(state.isPartial).toBe(true)
    expect(state.filters.categories).toEqual(['Large Cap'])
    expect(state.filters.amcs).toEqual(['HDFC'])

    act(() => {
      useAppStore.getState().setSession('tax-1', 'tax_expert', {})
    })
    state = useAppStore.getState()
    expect(state.taxSessionId).toBe('tax-1')

    act(() => {
      useAppStore.getState().setSession('eq-1', 'equity', {})
    })
    state = useAppStore.getState()
    expect(state.equitySessionId).toBe('eq-1')

    // setSessionById
    act(() => {
      useAppStore.getState().setSessionById('mf-2', 'mutual_funds')
      useAppStore.getState().setSessionById('tax-2', 'tax_expert')
      useAppStore.getState().setSessionById('eq-2', 'equity')
    })
    state = useAppStore.getState()
    expect(state.mfSessionId).toBe('mf-2')
    expect(state.taxSessionId).toBe('tax-2')
    expect(state.equitySessionId).toBe('eq-2')

    // clear individual session
    act(() => {
      useAppStore.getState().clearSession('mutual_funds')
    })
    state = useAppStore.getState()
    expect(state.mfSessionId).toBeNull()
    expect(state.taxSessionId).toBe('tax-2')
    expect(state.equitySessionId).toBe('eq-2')

    // clear all sessions
    act(() => {
      useAppStore.getState().clearSession()
    })
    state = useAppStore.getState()
    expect(state.mfSessionId).toBeNull()
    expect(state.taxSessionId).toBeNull()
    expect(state.equitySessionId).toBeNull()
  })

  it('updates filters and triggers refresh', () => {
    act(() => {
      useAppStore.getState().setFilters({ benchmark: 'Nifty Next 50', plan: 'Direct' })
    })
    expect(useAppStore.getState().filters.benchmark).toBe('Nifty Next 50')
    expect(useAppStore.getState().filters.plan).toBe('Direct')

    const before = useAppStore.getState().lastSynced
    act(() => {
      useAppStore.getState().triggerRefresh()
    })
    expect(useAppStore.getState().lastSynced).toBeGreaterThanOrEqual(before)
  })

  it('sets and updates compareFunds and compareBench', () => {
    act(() => {
      useAppStore.getState().setCompareFunds('sid-1', ['fundA', 'fundB'])
      useAppStore.getState().setCompareBench('sid-1', 'Nifty 50')
    })

    expect(useAppStore.getState().compareFunds['sid-1']).toEqual(['fundA', 'fundB'])
    expect(useAppStore.getState().compareBench['sid-1']).toBe('Nifty 50')
  })

  it('executes logout flow and calls api and authClient', async () => {
    act(() => {
      useAppStore.getState().setIdentity({ userId: 'u-1', pan: 'ABCDE1234F' })
    })

    await act(async () => {
      await useAppStore.getState().logout()
    })

    expect(api.post).toHaveBeenCalledWith('/auth/logout')
    expect(authClient.signOut).toHaveBeenCalled()
    expect(useAppStore.getState().userId).toBeNull()
    expect(useAppStore.getState().pan).toBeNull()
  })

  it('selectors return proper values according to active module and identity', () => {
    act(() => {
      useAppStore.getState().setIdentity({
        userId: 'user-xyz',
        pan: 'ABCDE1234F',
        role: 'admin',
        status: 'active',
      })
      useAppStore.getState().setSession('mf-10', 'mutual_funds', null)
      useAppStore.getState().setSession('tax-20', 'tax_expert', null)
      useAppStore.getState().setSession('eq-30', 'equity', null)
    })

    const { result: authResult } = renderHook(() => useIsAuthenticated())
    expect(authResult.current).toBe(true)

    const { result: userResult } = renderHook(() => useUserId())
    expect(userResult.current).toBe('user-xyz')

    const { result: panResult } = renderHook(() => usePan())
    expect(panResult.current).toBe('ABCDE1234F')

    const { result: roleResult } = renderHook(() => useUserRole())
    expect(roleResult.current).toBe('admin')

    const { result: statusResult } = renderHook(() => useUserStatus())
    expect(statusResult.current).toBe('active')

    // Module session selector
    act(() => {
      useAppStore.getState().setActiveModule('mutual_funds')
    })
    const { result: mfHook } = renderHook(() => useSessionId())
    expect(mfHook.current).toBe('mf-10')

    act(() => {
      useAppStore.getState().setActiveModule('tax_expert')
    })
    const { result: taxHook } = renderHook(() => useSessionId())
    expect(taxHook.current).toBe('tax-20')

    act(() => {
      useAppStore.getState().setActiveModule('indian_stocks')
    })
    const { result: eqHook } = renderHook(() => useSessionId())
    expect(eqHook.current).toBe('eq-30')
  })
  it('logout error-catch branch: still clears state when api call throws', async () => {
    vi.mocked(api.post).mockRejectedValueOnce(new Error('network error'))
    act(() => {
      useAppStore.getState().setIdentity({ userId: 'u-err', pan: 'ABCDE1234F' })
    })
    // Should not throw
    await act(async () => {
      await useAppStore.getState().logout()
    })
    // State is still cleared after the catch
    expect(useAppStore.getState().userId).toBeNull()
  })

  it('useSessionId returns null when activeModule is not a session-bearing module', () => {
    act(() => {
      useAppStore.getState().setActiveModule('mutual_funds')
      useAppStore.setState({ activeModule: 'dashboard' as any })
    })
    const { result } = renderHook(() => useSessionId())
    expect(result.current).toBeNull()
  })
})
