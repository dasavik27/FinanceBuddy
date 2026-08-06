import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor, act } from '@testing-library/react'
import { renderWithProviders } from './test/utils'
import App from './App'
import { useAppStore } from './shared/store/appStore'
import authClient from './shared/auth/authClient'
import { apiClient } from './shared/api/client'

type AuthCallback = (user: { id: string; email: string } | null) => void | Promise<void>
let authCallback: AuthCallback | null = null

vi.mock('./shared/auth/authClient', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./shared/auth/authClient')>()
  return {
    ...actual,
    default: {
      ...actual.default,
      isConfigured: true,
      onAuthStateChange: vi.fn((cb: AuthCallback) => {
        authCallback = cb
        return vi.fn()
      }),
      signOut: vi.fn().mockResolvedValue(undefined),
      checkSessionHealth: vi.fn().mockResolvedValue(true),
    },
    isPasswordSetupRequired: vi.fn(() => false),
    lookupAccessNoticeForEmails: vi.fn().mockResolvedValue({
      message: '',
      access_request_status: 'none',
      email: '',
    }),
  }
})

vi.mock('./shared/auth/authNotice', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./shared/auth/authNotice')>()
  return {
    ...actual,
    writeAuthNotice: vi.fn(),
    readAccessRequestEmail: vi.fn(() => null),
  }
})

vi.mock('./shared/api/client', () => ({
  apiClient: {
    getMe: vi.fn(),
  },
}))

vi.mock('./shared/components/layout/Layout', () => ({
  default: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="app-layout">{children}</div>
  ),
}))

vi.mock('./shared/components/layout/Dashboard', () => ({
  default: () => <div data-testid="app-dashboard">Dashboard</div>,
}))

async function flushAuth(user: { id: string; email: string } | null) {
  await act(async () => {
    await authCallback?.(user)
  })
}

describe('App routing shell', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authCallback = null
    useAppStore.getState().clearIdentity()
    vi.mocked(authClient.onAuthStateChange).mockImplementation((cb: AuthCallback) => {
      authCallback = cb
      return vi.fn()
    })
  })

  it('shows loading fallback while session is resolving', () => {
    renderWithProviders(<App />)
    expect(document.querySelector('.MuiSkeleton-root')).toBeTruthy()
  })

  it('renders Landing for anonymous visitors after session resolves', async () => {
    renderWithProviders(<App />)
    await flushAuth(null)

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /Finance Buddy/i })).toBeInTheDocument()
    })
  })

  it('renders authenticated layout for active users', async () => {
    vi.mocked(apiClient.getMe).mockResolvedValue({
      email: 'investor@test.com',
      display_name: 'Investor',
      pan: 'ABCDE1234F',
      status: 'active',
      role: 'user',
    } as any)

    act(() => {
      useAppStore.getState().setIdentity({
        userId: 'u-app',
        email: 'investor@test.com',
        status: 'active',
        role: 'user',
        pan: 'ABCDE1234F',
      })
    })

    renderWithProviders(<App />, { initialEntries: ['/dashboard'] })
    await flushAuth({ id: 'u-app', email: 'investor@test.com' })

    await waitFor(() => {
      expect(screen.getByTestId('app-layout')).toBeInTheDocument()
      expect(screen.getByTestId('app-dashboard')).toBeInTheDocument()
    })
  })

  it('shows suspended access screen for suspended accounts', async () => {
    vi.mocked(apiClient.getMe).mockResolvedValue({
      email: 'blocked@test.com',
      status: 'suspended',
      role: 'user',
    } as any)

    act(() => {
      useAppStore.getState().setIdentity({
        userId: 'u-suspended',
        email: 'blocked@test.com',
        status: 'suspended',
        role: 'user',
      })
    })

    renderWithProviders(<App />)
    await flushAuth({ id: 'u-suspended', email: 'blocked@test.com' })

    await waitFor(() => {
      expect(screen.getByText(/Account suspended/i)).toBeInTheDocument()
    })
  })

  it('shows pending access screen for pending accounts', async () => {
    vi.mocked(apiClient.getMe).mockResolvedValue({
      email: 'pending@test.com',
      status: 'pending',
      role: 'user',
    } as any)

    act(() => {
      useAppStore.getState().setIdentity({
        userId: 'u-pending',
        email: 'pending@test.com',
        status: 'pending',
        role: 'user',
      })
    })

    renderWithProviders(<App />)
    await flushAuth({ id: 'u-pending', email: 'pending@test.com' })

    await waitFor(() => {
      expect(screen.getByText(/Access pending/i)).toBeInTheDocument()
    })
  })

  it('signs out on 403 not_authorized from /auth/me', async () => {
    vi.mocked(apiClient.getMe).mockRejectedValue({
      response: {
        status: 403,
        data: {
          detail: 'not_authorized',
          message: 'Awaiting approval',
          access_request_status: 'pending',
        },
      },
    })

    renderWithProviders(<App />)
    await flushAuth({ id: 'u-denied', email: 'denied@test.com' })

    await waitFor(() => {
      expect(authClient.signOut).toHaveBeenCalled()
    })
  })
})
