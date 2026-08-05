import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useDebounce } from './useDebounce'
import { useMarketSummary, useMarketConfig } from './useMarket'
import { createTestQueryClient } from '../../test/utils'
import { QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import { apiClient } from '../api/client'

vi.mock('../api/client', () => ({
  apiClient: {
    getMarketSummary: vi.fn().mockResolvedValue([{ symbol: '^NSEI', name: 'NIFTY 50', price: 24500 }]),
    getMarketConfig: vi.fn().mockResolvedValue({ refresh_rate: 60 }),
  },
}))

describe('useDebounce', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns initial value immediately and debounces updates', () => {
    const { result, rerender } = renderHook(
      (props: { val: string; delay: number }) => useDebounce(props.val, props.delay),
      {
        initialProps: { val: 'initial', delay: 300 },
      }
    )

    expect(result.current).toBe('initial')

    rerender({ val: 'updated 1', delay: 300 })
    expect(result.current).toBe('initial')

    act(() => {
      vi.advanceTimersByTime(200)
    })
    expect(result.current).toBe('initial')

    rerender({ val: 'updated 2', delay: 300 })
    act(() => {
      vi.advanceTimersByTime(300)
    })
    expect(result.current).toBe('updated 2')
  })
})

describe('useMarket hooks', () => {
  it('useMarketSummary fetches market summary when enabled', async () => {
    const queryClient = createTestQueryClient()
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      React.createElement(QueryClientProvider, { client: queryClient }, children)
    )

    const { result } = renderHook(() => useMarketSummary(true), { wrapper })
    await vi.waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual([{ symbol: '^NSEI', name: 'NIFTY 50', price: 24500 }])
    expect(apiClient.getMarketSummary).toHaveBeenCalled()
  })

  it('useMarketConfig fetches market configuration', async () => {
    const queryClient = createTestQueryClient()
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      React.createElement(QueryClientProvider, { client: queryClient }, children)
    )

    const { result } = renderHook(() => useMarketConfig(), { wrapper })
    await vi.waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual({ refresh_rate: 60 })
    expect(apiClient.getMarketConfig).toHaveBeenCalled()
  })
})
