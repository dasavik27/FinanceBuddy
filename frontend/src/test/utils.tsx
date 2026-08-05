import React, { ReactElement } from 'react'
import { render, RenderOptions } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ThemeProvider, CssBaseline } from '@mui/material'
import { MemoryRouter, MemoryRouterProps } from 'react-router-dom'
import { theme } from '../shared/theme/theme'
import { useAppStore } from '../shared/store/appStore'

export interface ExtendedRenderOptions extends Omit<RenderOptions, 'wrapper'> {
  initialEntries?: MemoryRouterProps['initialEntries']
  queryClient?: QueryClient
}

export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: 0,
        gcTime: 0,
      },
      mutations: {
        retry: false,
      },
    },
  })
}

export function createWrapper(queryClient = createTestQueryClient()) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <ThemeProvider theme={theme}>
          <CssBaseline />
          <MemoryRouter>
            {children}
          </MemoryRouter>
        </ThemeProvider>
      </QueryClientProvider>
    )
  }
}

export function renderWithProviders(
  ui: ReactElement,
  {
    initialEntries = ['/'],
    queryClient = createTestQueryClient(),
    ...renderOptions
  }: ExtendedRenderOptions = {}
) {
  function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <ThemeProvider theme={theme}>
          <CssBaseline />
          <MemoryRouter initialEntries={initialEntries}>
            {children}
          </MemoryRouter>
        </ThemeProvider>
      </QueryClientProvider>
    )
  }

  return {
    user: userEvent.setup(),
    queryClient,
    ...render(ui, { wrapper: Wrapper, ...renderOptions }),
  }
}

export function resetAppStore() {
  useAppStore.setState({
    pan: null,
    userId: null,
    email: null,
    displayName: null,
    status: null,
    role: null,
    taxSlab: 30,
    taxRegime: 'new',
    activeModule: 'mutual_funds',
    mfSessionId: null,
    taxSessionId: null,
    equitySessionId: null,
    parseData: null,
    isPartial: false,
    filters: {
      benchmark: 'Nifty 50',
      categories: [],
      amcs: [],
      plan: 'All',
      minAlloc: 0,
    },
    compareFunds: {},
    compareBench: {},
  })
}

export * from '@testing-library/react'
export { userEvent }
