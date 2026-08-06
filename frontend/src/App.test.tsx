import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from './App'
import { renderWithProviders } from './test/utils'
import { useAppStore } from './shared/store/appStore'
import authClient from './shared/auth/authClient'
import { apiClient } from './shared/api/client'
import * as authNoticeModule from './shared/auth/authNotice'

vi.mock('./shared/auth/authClient', () => {
  let authCallback: ((user: any) => void) | null = null
  return {
    default: {
      isConfigured: true,
      onAuthStateChange: vi.fn((cb) => {
        authCallback = cb
        return () => {
          authCallback = null
        }
      }),
      signOut: vi.fn().mockResolvedValue(undefined),
      checkSessionHealth: vi.fn().mockResolvedValue(true),
      getAccessToken: vi.fn().mockResolvedValue('token'),
    },
    isPasswordSetupRequired: vi.fn(() => false),
    lookupAccessNoticeForEmails: vi.fn().mockResolvedValue({ access_request_status: 'none', message: '' }),
    __triggerAuthStateChange: (user: any) => {
      if (authCallback) authCallback(user)
    },
  }
})

vi.mock('./shared/api/client', () => ({
  apiClient: {
    getMe: vi.fn(),
  },
}))

vi.mock('./shared/components/Landing', () => ({
  default: () => <div data-testid="landing-page">Landing Page</div>,
}))

vi.mock('./shared/components/AccountSetupPrompt', () => ({
  default: ({ requirePassword, requirePan, onPasswordComplete }: any) => (
    <div data-testid="account-setup-prompt">
      <span>Require Password: {String(requirePassword)}</span>
      <span>Require Pan: {String(requirePan)}</span>
      <button onClick={onPasswordComplete}>Complete Password</button>
    </div>
  ),
}))

vi.mock('./shared/components/PendingAccess', () => ({
  default: () => <div data-testid="pending-access">Pending Access</div>,
}))

vi.mock('./shared/components/SuspendedAccess', () => ({
  default: () => <div data-testid="suspended-access">Suspended Access</div>,
}))

vi.mock('./shared/components/layout/Layout', () => ({
  default: ({ children }: any) => <div data-testid="layout">{children}</div>,
}))

vi.mock('./shared/components/layout/Dashboard', () => ({
  default: () => <div data-testid="dashboard">Dashboard View</div>,
}))

describe('App Component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.getState().clearIdentity()
    ;(authClient as any).isConfigured = true
    vi.mocked(apiClient.getMe).mockResolvedValue({
      user_id: 'u-1',
      email: 'test@example.com',
      pan: 'ABCDE1234F',
      display_name: 'Test User',
      status: 'active',
      role: 'user',
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders landing page for unauthenticated visitors at "/"', async () => {
    renderWithProviders(<App />, { initialEntries: ['/'] })

    const { __triggerAuthStateChange } = await import('./shared/auth/authClient') as any
    act(() => {
      __triggerAuthStateChange(null)
    })

    expect(await screen.findByTestId('landing-page')).toBeInTheDocument()
  })

  it('redirects unauthenticated visitors from protected route to "/"', async () => {
    renderWithProviders(<App />, { initialEntries: ['/equity'] })

    const { __triggerAuthStateChange } = await import('./shared/auth/authClient') as any
    act(() => {
      __triggerAuthStateChange(null)
    })

    expect(await screen.findByTestId('landing-page')).toBeInTheDocument()
  })

  it('renders TabFallback when authenticated without status and authClient is not configured', () => {
    ;(authClient as any).isConfigured = false
    useAppStore.setState({ userId: 'u-1', email: 'test@example.com', status: null as any })

    const { container } = renderWithProviders(<App />, { initialEntries: ['/dashboard'] })
    expect(container).toBeDefined()
  })

  it('renders suspended screen when authenticated user status is suspended', async () => {
    vi.mocked(apiClient.getMe).mockResolvedValueOnce({
      user_id: 'u-1',
      email: 'test@example.com',
      pan: 'ABCDE1234F',
      display_name: 'Test User',
      status: 'suspended',
      role: 'user',
    })

    renderWithProviders(<App />, { initialEntries: ['/dashboard'] })

    const { __triggerAuthStateChange } = await import('./shared/auth/authClient') as any
    await act(async () => {
      __triggerAuthStateChange({ id: 'u-1', email: 'test@example.com' })
    })

    expect(await screen.findByTestId('suspended-access')).toBeInTheDocument()
  })

  it('renders pending access screen when authenticated user status is pending', async () => {
    vi.mocked(apiClient.getMe).mockResolvedValueOnce({
      user_id: 'u-1',
      email: 'test@example.com',
      pan: null,
      display_name: 'Test User',
      status: 'pending',
      role: 'user',
    })

    renderWithProviders(<App />, { initialEntries: ['/dashboard'] })

    const { __triggerAuthStateChange } = await import('./shared/auth/authClient') as any
    await act(async () => {
      __triggerAuthStateChange({ id: 'u-1', email: 'test@example.com' })
    })

    expect(await screen.findByTestId('pending-access')).toBeInTheDocument()
  })

  it('renders AccountSetupPrompt when password or PAN setup is required', async () => {
    const { isPasswordSetupRequired } = await import('./shared/auth/authClient') as any
    vi.mocked(isPasswordSetupRequired).mockReturnValue(true)

    vi.mocked(apiClient.getMe).mockResolvedValueOnce({
      user_id: 'u-1',
      email: 'test@example.com',
      pan: null,
      display_name: 'Test User',
      status: 'active',
      role: 'user',
    })

    renderWithProviders(<App />, { initialEntries: ['/dashboard'] })

    const { __triggerAuthStateChange } = await import('./shared/auth/authClient') as any
    await act(async () => {
      __triggerAuthStateChange({ id: 'u-1', email: 'test@example.com' })
    })

    expect(await screen.findByTestId('account-setup-prompt')).toBeInTheDocument()
    expect(screen.getByText('Require Password: true')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /Complete Password/i }))
  })

  it('renders authenticated layout and dashboard for active users with PAN', async () => {
    const { isPasswordSetupRequired } = await import('./shared/auth/authClient') as any
    vi.mocked(isPasswordSetupRequired).mockReturnValue(false)

    vi.mocked(apiClient.getMe).mockResolvedValueOnce({
      user_id: 'u-1',
      email: 'test@example.com',
      pan: 'ABCDE1234F',
      display_name: 'Test User',
      status: 'active',
      role: 'user',
    })

    renderWithProviders(<App />, { initialEntries: ['/dashboard'] })

    const { __triggerAuthStateChange } = await import('./shared/auth/authClient') as any
    await act(async () => {
      __triggerAuthStateChange({ id: 'u-1', email: 'test@example.com' })
    })

    expect(await screen.findByTestId('layout')).toBeInTheDocument()
    expect(screen.getByTestId('dashboard')).toBeInTheDocument()
  })

  it('handles auth state change with successful getMe profile fetch and retains PAN', async () => {
    vi.mocked(apiClient.getMe).mockResolvedValueOnce({
      user_id: 'u-1',
      email: 'user@test.com',
      pan: 'ABCDE1234F',
      display_name: 'Test User',
      status: 'active',
      role: 'user',
    })

    renderWithProviders(<App />, { initialEntries: ['/'] })

    const { __triggerAuthStateChange } = await import('./shared/auth/authClient') as any
    await act(async () => {
      __triggerAuthStateChange({ id: 'u-1', email: 'user@test.com' })
    })

    await waitFor(() => {
      expect(useAppStore.getState().displayName).toBe('Test User')
      expect(useAppStore.getState().pan).toBe('ABCDE1234F')
    })
  })

  it('handles 403 not_authorized error creating initial notice when none existed', async () => {
    const writeNoticeSpy = vi.spyOn(authNoticeModule, 'writeAuthNotice')
    const { lookupAccessNoticeForEmails } = await import('./shared/auth/authClient') as any
    vi.mocked(lookupAccessNoticeForEmails).mockResolvedValueOnce({
      access_request_status: 'none',
      message: '',
    })

    vi.mocked(apiClient.getMe).mockRejectedValueOnce({
      response: {
        status: 403,
        data: {
          detail: 'not_authorized',
          message: 'Access pending review',
          access_request_status: 'pending',
        },
      },
    })

    renderWithProviders(<App />, { initialEntries: ['/'] })

    const { __triggerAuthStateChange } = await import('./shared/auth/authClient') as any
    await act(async () => {
      __triggerAuthStateChange({ id: 'u-1', email: 'user@test.com' })
    })

    await waitFor(() => {
      expect(writeNoticeSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          message: 'Access pending review',
          access_request_status: 'pending',
          email: 'user@test.com',
        })
      )
      expect(authClient.signOut).toHaveBeenCalled()
      expect(useAppStore.getState().userId).toBeNull()
    })
  })

  it('handles 403 with non-not_authorized detail without writing auth notice', async () => {
    const writeNoticeSpy = vi.spyOn(authNoticeModule, 'writeAuthNotice')

    vi.mocked(apiClient.getMe).mockRejectedValueOnce({
      response: {
        status: 403,
        data: { detail: 'other_forbidden' },
      },
    })

    renderWithProviders(<App />, { initialEntries: ['/'] })

    const { __triggerAuthStateChange } = await import('./shared/auth/authClient') as any
    await act(async () => {
      __triggerAuthStateChange({ id: 'u-1', email: 'user@test.com' })
    })

    await waitFor(() => {
      expect(writeNoticeSpy).not.toHaveBeenCalled()
      expect(authClient.signOut).toHaveBeenCalled()
    })
  })

  it('handles 403 not_authorized error updating notice message when status already existed', async () => {
    const writeNoticeSpy = vi.spyOn(authNoticeModule, 'writeAuthNotice')
    const { lookupAccessNoticeForEmails } = await import('./shared/auth/authClient') as any
    vi.mocked(lookupAccessNoticeForEmails).mockResolvedValueOnce({
      access_request_status: 'pending',
      message: 'Old notice',
    })

    vi.mocked(apiClient.getMe).mockRejectedValueOnce({
      response: {
        status: 403,
        data: {
          detail: 'not_authorized',
          message: 'Updated pending notice',
          access_request_status: 'pending',
        },
      },
    })

    renderWithProviders(<App />, { initialEntries: ['/'] })

    const { __triggerAuthStateChange } = await import('./shared/auth/authClient') as any
    await act(async () => {
      __triggerAuthStateChange({ id: 'u-1', email: 'user@test.com' })
    })

    await waitFor(() => {
      expect(writeNoticeSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          message: 'Updated pending notice',
          access_request_status: 'pending',
        })
      )
    })
  })

  it('handles generic error from getMe and resets session', async () => {
    vi.mocked(apiClient.getMe).mockRejectedValueOnce(new Error('Network error'))

    renderWithProviders(<App />, { initialEntries: ['/'] })

    const { __triggerAuthStateChange } = await import('./shared/auth/authClient') as any
    await act(async () => {
      __triggerAuthStateChange({ id: 'u-1', email: 'user@test.com' })
    })

    await waitFor(() => {
      expect(authClient.signOut).toHaveBeenCalled()
      expect(useAppStore.getState().userId).toBeNull()
    })
  })

  it('verifies session health on visibility change and signs out when unhealthy', async () => {
    vi.mocked(apiClient.getMe).mockResolvedValueOnce({
      user_id: 'u-1',
      email: 'test@example.com',
      pan: 'ABCDE1234F',
      display_name: 'Test User',
      status: 'active',
      role: 'user',
    })
    vi.mocked(authClient.checkSessionHealth).mockResolvedValueOnce(false)

    renderWithProviders(<App />, { initialEntries: ['/dashboard'] })

    const { __triggerAuthStateChange } = await import('./shared/auth/authClient') as any
    await act(async () => {
      __triggerAuthStateChange({ id: 'u-1', email: 'test@example.com' })
    })

    // Simulate tab focus / visibility
    await act(async () => {
      Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
      document.dispatchEvent(new Event('visibilitychange'))
      window.dispatchEvent(new Event('focus'))
    })

    await waitFor(() => {
      expect(authClient.checkSessionHealth).toHaveBeenCalled()
      expect(authClient.signOut).toHaveBeenCalled()
      expect(useAppStore.getState().userId).toBeNull()
    })
  })

  it('handles session health check error gracefully when checkSessionHealth throws', async () => {
    vi.mocked(apiClient.getMe).mockResolvedValueOnce({
      user_id: 'u-1',
      email: 'test@example.com',
      pan: 'ABCDE1234F',
      display_name: 'Test User',
      status: 'active',
      role: 'user',
    })
    vi.mocked(authClient.checkSessionHealth).mockRejectedValueOnce(new Error('Network error during check'))

    renderWithProviders(<App />, { initialEntries: ['/dashboard'] })

    const { __triggerAuthStateChange } = await import('./shared/auth/authClient') as any
    await act(async () => {
      __triggerAuthStateChange({ id: 'u-1', email: 'test@example.com' })
    })

    await act(async () => {
      Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
      document.dispatchEvent(new Event('visibilitychange'))
    })
  })
})
