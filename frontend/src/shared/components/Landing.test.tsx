import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
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
    message: 'Access message details',
    severity: 'info',
    access_request_status: status,
  })),
  bannerForError: vi.fn((err) => ({
    title: 'Sign-in failed',
    message: String(err),
    severity: 'error',
  })),
  bannerForOAuthNoAccount: vi.fn(),
  consumeOAuthErrorFromUrl: vi.fn(() => null),
  lookupAccessNoticeForEmails: vi.fn().mockResolvedValue(null),
}))

describe('Landing Page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    sessionStorage.clear()
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

    const emailInput = screen.getByPlaceholderText(/Email address/i)
    const pwInput = screen.getByPlaceholderText(/Password/i)
    const submitBtn = screen.getByRole('button', { name: /Sign In to Dashboard/i })

    await userEvent.type(emailInput, 'investor@example.com')
    await userEvent.type(pwInput, 'SecretPassword123!')
    await userEvent.click(submitBtn)

    expect(authClient.signInWithEmail).toHaveBeenCalledWith('investor@example.com', 'SecretPassword123!')
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
    await userEvent.click(reqAccessBtn)

    expect(await screen.findByText('Join the private wealth intelligence beta')).toBeInTheDocument()

    const nameInput = screen.getByPlaceholderText('e.g. Rahul Sharma')
    const emailInput = screen.getByPlaceholderText('name@example.com')
    const submitModalBtn = screen.getByRole('button', { name: /Submit Access Request/i })

    await userEvent.type(nameInput, 'Alex Investor')
    await userEvent.type(emailInput, 'alex@example.com')
    await userEvent.click(submitModalBtn)

    await vi.waitFor(() => {
      expect(authClient.submitAccessRequest).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'Alex Investor',
          email: 'alex@example.com',
        })
      )
    })
  })
})
