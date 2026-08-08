import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../test/utils'
import AccountSetupPrompt from './AccountSetupPrompt'
import { useAppStore } from '../store/appStore'
import authClient from '../auth/authClient'
import { apiClient } from '../api/client'

vi.mock('../auth/authClient', () => ({
  default: {
    updatePassword: vi.fn().mockResolvedValue(undefined),
  },
}))

vi.mock('../api/client', () => ({
  apiClient: {
    setProfilePan: vi.fn().mockResolvedValue({ status: 'ok', pan: 'ABCDE1234F' }),
  },
}))

describe('AccountSetupPrompt', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.getState().setIdentity({
      userId: 'u-prompt',
      email: 'user@financebuddy.com',
      pan: null,
      status: 'active',
      role: 'user',
    })
  })

  it('renders password and PAN setup form when both are required', () => {
    renderWithProviders(
      <AccountSetupPrompt
        requirePassword={true}
        requirePan={true}
        onPasswordComplete={vi.fn()}
      />
    )

    expect(screen.getByText('Finish account setup')).toBeInTheDocument()
    expect(screen.getByLabelText(/New password/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/Confirm password/i)).toBeInTheDocument()
    expect(screen.getByPlaceholderText('ABCDE1234F')).toBeInTheDocument()
  })

  it('validates password length and matching confirmation', async () => {
    renderWithProviders(
      <AccountSetupPrompt
        requirePassword={true}
        requirePan={false}
        onPasswordComplete={vi.fn()}
      />
    )

    const pwInput = screen.getByLabelText(/^New password/i)
    const confirmInput = screen.getByLabelText(/Confirm password/i)
    const submitBtn = screen.getByRole('button', { name: /Save password & continue/i })

    // Short password
    await userEvent.type(pwInput, 'short')
    await userEvent.click(submitBtn)
    expect(screen.getByText('Password must be at least 8 characters.')).toBeInTheDocument()

    // Mismatched confirmation
    await userEvent.clear(pwInput)
    await userEvent.type(pwInput, 'Secret123!')
    await userEvent.type(confirmInput, 'Secret456!')
    await userEvent.click(submitBtn)
    expect(screen.getByText('Passwords do not match.')).toBeInTheDocument()
  })

  it('validates PAN format when PAN is required', async () => {
    renderWithProviders(
      <AccountSetupPrompt
        requirePassword={false}
        requirePan={true}
        onPasswordComplete={vi.fn()}
      />
    )

    const panInput = screen.getByPlaceholderText('ABCDE1234F')
    const submitBtn = screen.getByRole('button', { name: /Continue to dashboard/i })

    await userEvent.type(panInput, 'INVALID_PAN')
    await userEvent.click(submitBtn)
    expect(screen.getByText(/Invalid PAN format/i)).toBeInTheDocument()
  })

  it('submits valid password and PAN successfully and triggers completion', async () => {
    const onComplete = vi.fn()
    renderWithProviders(
      <AccountSetupPrompt
        requirePassword={true}
        requirePan={true}
        onPasswordComplete={onComplete}
      />
    )

    const pwInput = screen.getByLabelText(/^New password/i)
    const confirmInput = screen.getByLabelText(/Confirm password/i)
    const panInput = screen.getByPlaceholderText('ABCDE1234F')
    const submitBtn = screen.getByRole('button', { name: /Save & continue/i })

    await userEvent.type(pwInput, 'SuperSecret123!')
    await userEvent.type(confirmInput, 'SuperSecret123!')
    await userEvent.type(panInput, 'ABCDE1234F')
    await userEvent.click(submitBtn)

    await vi.waitFor(() => {
      expect(authClient.updatePassword).toHaveBeenCalledWith('SuperSecret123!')
      expect(apiClient.setProfilePan).toHaveBeenCalledWith('ABCDE1234F')
      expect(onComplete).toHaveBeenCalled()
    })
  })

  it('returns null when neither password nor PAN is required', () => {
    const { container } = renderWithProviders(
      <AccountSetupPrompt
        requirePassword={false}
        requirePan={false}
        onPasswordComplete={vi.fn()}
      />
    )
    expect(container.querySelector('form')).toBeNull()
  })

  it('shows password-only and PAN-only titles', () => {
    const { unmount } = renderWithProviders(
      <AccountSetupPrompt requirePassword={true} requirePan={false} onPasswordComplete={vi.fn()} />
    )
    expect(screen.getByText('Create your password')).toBeInTheDocument()
    unmount()

    renderWithProviders(
      <AccountSetupPrompt requirePassword={false} requirePan={true} onPasswordComplete={vi.fn()} />
    )
    expect(screen.getByText('Link your PAN')).toBeInTheDocument()
  })

  it('requires PAN value before submit and surfaces API errors', async () => {
    vi.mocked(apiClient.setProfilePan).mockRejectedValueOnce({
      response: { data: { detail: 'PAN taken' } },
    })
    renderWithProviders(
      <AccountSetupPrompt requirePassword={false} requirePan={true} onPasswordComplete={vi.fn()} />
    )
    await userEvent.click(screen.getByRole('button', { name: /Continue to dashboard/i }))
    expect(screen.getByText(/Please enter your 10-character PAN/i)).toBeInTheDocument()

    await userEvent.type(screen.getByPlaceholderText('ABCDE1234F'), 'ABCDE1234F')
    await userEvent.click(screen.getByRole('button', { name: /Continue to dashboard/i }))
    expect(await screen.findByText('PAN taken')).toBeInTheDocument()
  })

  it('toggles password visibility and signs out', async () => {
    const logout = vi.fn().mockResolvedValue(undefined)
    useAppStore.setState({ logout })
    renderWithProviders(
      <AccountSetupPrompt requirePassword={true} requirePan={false} onPasswordComplete={vi.fn()} />
    )
    const pw = screen.getByLabelText(/^New password/i)
    expect(pw).toHaveAttribute('type', 'password')
    const toggle = screen.getAllByRole('button').find((b) =>
      b.querySelector('[data-testid="VisibilityIcon"]')
    )!
    await userEvent.click(toggle)
    expect(pw).toHaveAttribute('type', 'text')

    await userEvent.click(screen.getByRole('button', { name: /Sign out/i }))
    expect(logout).toHaveBeenCalled()
  })
})
