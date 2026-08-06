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
  })
})
