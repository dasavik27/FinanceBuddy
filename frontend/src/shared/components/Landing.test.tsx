import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../test/utils'
import Landing from './Landing'
import authClient from '../auth/authClient'

vi.mock('../auth/authClient', () => ({
  default: {
    isConfigured: true,
    signInWithEmail: vi.fn(),
    signInWithGoogle: vi.fn(),
    checkAccessStatus: vi.fn(),
    submitAccessRequest: vi.fn(),
  },
  bannerForAccessStatus: vi.fn((status) => ({
    title: `Status: ${status}`,
    detail: 'Access message details',
    severity: 'info',
    access_request_status: status ?? 'none',
  })),
  bannerForError: vi.fn((err) => ({
    title: 'Sign-in failed',
    detail: String(err),
    severity: 'error',
    access_request_status: null,
  })),
  bannerForOAuthNoAccount: vi.fn(() => ({
    title: 'No account found',
    detail: 'Request access to continue.',
    severity: 'info',
    access_request_status: 'none',
  })),
  consumeOAuthErrorFromUrl: vi.fn(() => null),
  lookupAccessNoticeForEmails: vi.fn().mockResolvedValue(null),
}))

vi.mock('../auth/authNotice', async () => {
  const actual = await vi.importActual<typeof import('../auth/authNotice')>('../auth/authNotice')
  return {
    ...actual,
    readAuthNotice: vi.fn(() => null),
    readAccessRequestEmail: vi.fn(() => null),
    rememberAccessRequestEmail: vi.fn(),
    clearAccessRequestEmail: vi.fn(),
  }
})

import {
  bannerForAccessStatus,
  bannerForError,
  bannerForOAuthNoAccount,
  consumeOAuthErrorFromUrl,
} from '../auth/authClient'
import { readAuthNotice } from '../auth/authNotice'

describe('Landing Page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    sessionStorage.clear()
    Object.defineProperty(authClient, 'isConfigured', { value: true, configurable: true })
    vi.mocked(consumeOAuthErrorFromUrl).mockReturnValue(null)
    vi.mocked(readAuthNotice).mockReturnValue(null)
  })

  it('renders landing title, hero tagline, and sign-in inputs', () => {
    renderWithProviders(<Landing />)

    expect(screen.getByRole('heading', { name: /Finance Buddy/i })).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/Email address/i)).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/Password/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Sign In to Dashboard/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Continue with Google/i })).toBeInTheDocument()
  })

  it('triggers signInWithEmail when valid credentials are submitted', async () => {
    vi.mocked(authClient.signInWithEmail).mockResolvedValueOnce({
      user: { id: 'u-123' },
      session: { access_token: 'token-abc' },
    } as any)

    renderWithProviders(<Landing />)

    fireEvent.change(screen.getByPlaceholderText(/Email address/i), {
      target: { value: 'investor@example.com' },
    })
    fireEvent.change(screen.getByPlaceholderText(/Password/i), {
      target: { value: 'SecretPassword123!' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Sign In to Dashboard/i }))

    await waitFor(() => {
      expect(authClient.signInWithEmail).toHaveBeenCalledWith('investor@example.com', 'SecretPassword123!')
    })
  })

  it('triggers Google OAuth on button click', async () => {
    renderWithProviders(<Landing />)
    const googleBtn = screen.getByRole('button', { name: /Continue with Google/i })
    await userEvent.click(googleBtn)
    expect(authClient.signInWithGoogle).toHaveBeenCalled()
  })

  it('opens request access modal and submits application', async () => {
    vi.mocked(authClient.submitAccessRequest).mockResolvedValueOnce({
      status: 'pending',
      message: 'Your request has been received.',
    } as any)

    renderWithProviders(<Landing />)

    const reqAccessBtn = screen.getByRole('button', { name: /Request Early Access/i })
    fireEvent.click(reqAccessBtn)

    expect(await screen.findByRole('heading', { name: /Request Access/i })).toBeInTheDocument()
    expect(screen.getByText(/Join the private wealth intelligence beta/i)).toBeInTheDocument()

    const nameInput = screen.getByPlaceholderText('e.g. Rahul Sharma')
    const emailInput = screen.getByPlaceholderText('name@example.com')
    const submitModalBtn = screen.getByRole('button', { name: /Submit Access Request/i })

    fireEvent.change(nameInput, { target: { value: 'Alex Investor' } })
    fireEvent.change(emailInput, { target: { value: 'alex@example.com' } })
    fireEvent.click(submitModalBtn)

    await waitFor(() => {
      expect(authClient.submitAccessRequest).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'Alex Investor',
          email: 'alex@example.com',
        })
      )
    })
    expect(await screen.findByText('Your request has been received.')).toBeInTheDocument()
  })

  it('shows validation banner when email/password missing on submit', async () => {
    renderWithProviders(<Landing />)
    fireEvent.click(screen.getByRole('button', { name: /Sign In to Dashboard/i }))
    await waitFor(() => {
      expect(bannerForError).toHaveBeenCalledWith('Please enter both email and password.')
    })
  })

  it('toggles password visibility', async () => {
    renderWithProviders(<Landing />)
    const password = screen.getByPlaceholderText(/Password/i)
    expect(password).toHaveAttribute('type', 'password')
    const toggle = password.parentElement?.querySelector('button') as HTMLButtonElement
    await userEvent.click(toggle)
    expect(password).toHaveAttribute('type', 'text')
  })

  it('on email sign-in failure applies access status when check succeeds', async () => {
    vi.mocked(authClient.signInWithEmail).mockRejectedValueOnce(new Error('bad creds'))
    vi.mocked(authClient.checkAccessStatus).mockResolvedValueOnce({
      access_request_status: 'pending',
    } as any)

    renderWithProviders(<Landing />)
    fireEvent.change(screen.getByPlaceholderText(/Email address/i), {
      target: { value: 'pending@example.com' },
    })
    fireEvent.change(screen.getByPlaceholderText(/Password/i), {
      target: { value: 'wrong-pass' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Sign In to Dashboard/i }))

    await waitFor(() => {
      expect(authClient.checkAccessStatus).toHaveBeenCalledWith('pending@example.com')
      expect(bannerForAccessStatus).toHaveBeenCalledWith('pending')
    })
  })

  it('on email sign-in failure falls back to invalid password when status check fails', async () => {
    vi.mocked(authClient.signInWithEmail).mockRejectedValueOnce(new Error('bad creds'))
    vi.mocked(authClient.checkAccessStatus).mockRejectedValueOnce(new Error('offline'))

    renderWithProviders(<Landing />)
    fireEvent.change(screen.getByPlaceholderText(/Email address/i), {
      target: { value: 'user@example.com' },
    })
    fireEvent.change(screen.getByPlaceholderText(/Password/i), {
      target: { value: 'wrong-pass' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Sign In to Dashboard/i }))

    await waitFor(() => {
      expect(bannerForError).toHaveBeenCalledWith('Invalid email or password.')
    })
  })

  it('shows OAuth no-account banner when Google auth is not configured', async () => {
    Object.defineProperty(authClient, 'isConfigured', { value: false, configurable: true })
    renderWithProviders(<Landing />)
    await userEvent.click(screen.getByRole('button', { name: /Continue with Google/i }))
    await waitFor(() => {
      expect(bannerForOAuthNoAccount).toHaveBeenCalled()
    })
  })

  it('on Google failure without email shows OAuth no-account banner', async () => {
    vi.mocked(authClient.signInWithGoogle).mockRejectedValueOnce(new Error('oauth failed'))
    renderWithProviders(<Landing />)
    await userEvent.click(screen.getByRole('button', { name: /Continue with Google/i }))
    await waitFor(() => {
      expect(bannerForOAuthNoAccount).toHaveBeenCalled()
    })
  })

  it('on Google failure with email applies access status', async () => {
    vi.mocked(authClient.signInWithGoogle).mockRejectedValueOnce(new Error('oauth failed'))
    vi.mocked(authClient.checkAccessStatus).mockResolvedValueOnce({
      access_request_status: 'none',
    } as any)

    renderWithProviders(<Landing />)
    fireEvent.change(screen.getByPlaceholderText(/Email address/i), {
      target: { value: 'google@example.com' },
    })
    await userEvent.click(screen.getByRole('button', { name: /Continue with Google/i }))

    await waitFor(() => {
      expect(authClient.checkAccessStatus).toHaveBeenCalledWith('google@example.com')
    })
  })

  it('surfaces already_submitted message from access request API', async () => {
    vi.mocked(authClient.submitAccessRequest).mockResolvedValueOnce({
      status: 'already_submitted',
      message: '',
    } as any)

    renderWithProviders(<Landing />)
    fireEvent.click(screen.getByRole('button', { name: /Request Early Access/i }))
    expect(await screen.findByRole('heading', { name: /Request Access/i })).toBeInTheDocument()

    fireEvent.change(screen.getByPlaceholderText('e.g. Rahul Sharma'), {
      target: { value: 'Alex' },
    })
    fireEvent.change(screen.getByPlaceholderText('name@example.com'), {
      target: { value: 'alex@example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Submit Access Request/i }))

    expect(
      await screen.findByText(/Your access request is already pending/i),
    ).toBeInTheDocument()
  })

  it('surfaces request submit API errors', async () => {
    vi.mocked(authClient.submitAccessRequest).mockRejectedValueOnce(new Error('Server down'))
    renderWithProviders(<Landing />)
    fireEvent.click(screen.getByRole('button', { name: /Request Early Access/i }))
    fireEvent.change(await screen.findByPlaceholderText('e.g. Rahul Sharma'), {
      target: { value: 'Alex' },
    })
    fireEvent.change(screen.getByPlaceholderText('name@example.com'), {
      target: { value: 'alex@example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Submit Access Request/i }))
    expect(await screen.findByText('Server down')).toBeInTheDocument()
  })

  it('shows stored auth notice banner on mount', async () => {
    vi.mocked(readAuthNotice).mockReturnValueOnce({
      message: 'Pending',
      access_request_status: 'pending',
    })
    renderWithProviders(<Landing />)
    await waitFor(() => {
      expect(bannerForAccessStatus).toHaveBeenCalledWith('pending')
    })
  })

  it('shows OAuth no-account banner when URL has oauth error', async () => {
    vi.mocked(consumeOAuthErrorFromUrl).mockReturnValueOnce('access_denied')
    renderWithProviders(<Landing />)
    await waitFor(() => {
      expect(bannerForOAuthNoAccount).toHaveBeenCalled()
    })
  })

  it('check status requires email then applies access status', async () => {
    vi.mocked(bannerForAccessStatus).mockReturnValue({
      title: 'Status: none',
      detail: 'Access message details',
      severity: 'info',
      access_request_status: 'none',
    })
    renderWithProviders(<Landing />)

    // Force banner with raise/check actions via failed sign-in status path first
    vi.mocked(authClient.signInWithEmail).mockRejectedValueOnce(new Error('bad'))
    vi.mocked(authClient.checkAccessStatus).mockResolvedValueOnce({
      access_request_status: 'none',
    } as any)
    fireEvent.change(screen.getByPlaceholderText(/Email address/i), {
      target: { value: 'check@example.com' },
    })
    fireEvent.change(screen.getByPlaceholderText(/Password/i), {
      target: { value: 'x' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Sign In to Dashboard/i }))
    await waitFor(() => expect(bannerForAccessStatus).toHaveBeenCalled())

    // Clear email and hit Check status → email needed banner
    fireEvent.change(screen.getByPlaceholderText(/Email address/i), { target: { value: '' } })
    const checkBtn = await screen.findByRole('button', { name: /Check status/i })
    fireEvent.click(checkBtn)
    expect(await screen.findByText(/Email needed/i)).toBeInTheDocument()

    fireEvent.change(screen.getByPlaceholderText(/Email address/i), {
      target: { value: 'check@example.com' },
    })
    vi.mocked(authClient.checkAccessStatus).mockResolvedValueOnce({
      access_request_status: 'pending',
    } as any)
    fireEvent.click(screen.getByRole('button', { name: /Check status/i }))
    await waitFor(() => {
      expect(authClient.checkAccessStatus).toHaveBeenCalledWith('check@example.com')
    })
  })

  it('check status surfaces API errors', async () => {
    vi.mocked(authClient.signInWithEmail).mockRejectedValueOnce(new Error('bad'))
    vi.mocked(authClient.checkAccessStatus).mockResolvedValueOnce({
      access_request_status: 'none',
    } as any)
    renderWithProviders(<Landing />)
    fireEvent.change(screen.getByPlaceholderText(/Email address/i), {
      target: { value: 'err@example.com' },
    })
    fireEvent.change(screen.getByPlaceholderText(/Password/i), { target: { value: 'x' } })
    fireEvent.click(screen.getByRole('button', { name: /Sign In to Dashboard/i }))
    await screen.findByRole('button', { name: /Check status/i })

    vi.mocked(authClient.checkAccessStatus).mockRejectedValueOnce(new Error('down'))
    fireEvent.click(screen.getByRole('button', { name: /Check status/i }))
    await waitFor(() => {
      expect(bannerForError).toHaveBeenCalledWith('Could not check status. Please try again.')
    })
  })

  it('closes request access modal and fills email from sign-in field', async () => {
    renderWithProviders(<Landing />)
    fireEvent.change(screen.getByPlaceholderText(/Email address/i), {
      target: { value: 'prefill@example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Request Early Access/i }))
    expect(await screen.findByRole('heading', { name: /Request Access/i })).toBeInTheDocument()
    expect(screen.getByPlaceholderText('name@example.com')).toHaveValue('prefill@example.com')

    fireEvent.change(screen.getByPlaceholderText('e.g. Rahul Sharma'), {
      target: { value: 'Alex' },
    })
    fireEvent.mouseDown(screen.getByRole('combobox'))
    fireEvent.click(await screen.findByText(/High Net-Worth Individual/i))
    fireEvent.change(
      screen.getByPlaceholderText(/Looking for unified stocks/i),
      { target: { value: 'Interested in beta' } },
    )
    await userEvent.click(screen.getByTestId('CloseIcon'))
    await waitFor(() => {
      expect(screen.queryByRole('heading', { name: /Request Access/i })).not.toBeInTheDocument()
    })
  })
})
