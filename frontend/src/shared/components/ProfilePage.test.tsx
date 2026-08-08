import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../test/utils'
import ProfilePage from './ProfilePage'
import { useAppStore } from '../store/appStore'
import { apiClient } from '../api/client'
import authClient from '../auth/authClient'

vi.mock('../api/client', () => ({
  apiClient: {
    updateProfile: vi.fn().mockResolvedValue({ status: 'ok', display_name: 'Jane Doe' }),
    setProfilePan: vi.fn().mockResolvedValue({ status: 'ok', pan: 'ABCDE1234F' }),
  },
}))

vi.mock('../auth/authClient', () => ({
  default: {
    updatePassword: vi.fn().mockResolvedValue(undefined),
  },
}))

describe('ProfilePage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.getState().setIdentity({
      userId: 'u-profile',
      email: 'jane@example.com',
      displayName: 'Jane Original',
      pan: null,
      role: 'user',
      status: 'active',
    })
  })

  it('renders profile cards for Display Name, PAN, and Password', () => {
    renderWithProviders(<ProfilePage />)

    expect(screen.getByText('Profile')).toBeInTheDocument()
    expect(screen.getByText('Account')).toBeInTheDocument()
    expect(screen.getAllByText('Display name').length).toBeGreaterThan(0)
    expect(screen.getAllByText('PAN').length).toBeGreaterThan(0)
    expect(screen.getByText('Password')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Jane Original')).toBeInTheDocument()
  })

  it('updates display name successfully', async () => {
    renderWithProviders(<ProfilePage />)

    const nameInput = screen.getByDisplayValue('Jane Original')
    const saveNameBtn = screen.getByRole('button', { name: /Save name/i })

    await userEvent.clear(nameInput)
    await userEvent.type(nameInput, 'Jane Doe')
    await userEvent.click(saveNameBtn)

    await vi.waitFor(() => {
      expect(apiClient.updateProfile).toHaveBeenCalledWith({ display_name: 'Jane Doe' })
    })
  })

  it('links PAN successfully', async () => {
    renderWithProviders(<ProfilePage />)

    const panInput = screen.getByPlaceholderText('ABCDE1234F')
    const linkPanBtn = screen.getByRole('button', { name: /Save PAN/i })

    await userEvent.type(panInput, 'ABCDE1234F')
    await userEvent.click(linkPanBtn)

    await vi.waitFor(() => {
      expect(apiClient.setProfilePan).toHaveBeenCalledWith('ABCDE1234F')
    })
  })

  it('updates password when confirmed and validated', async () => {
    renderWithProviders(<ProfilePage />)

    const newPwInput = screen.getByLabelText(/^New password/i)
    const confirmPwInput = screen.getByLabelText(/^Confirm password/i)
    const updatePwBtn = screen.getByRole('button', { name: /Update password/i })

    await userEvent.type(newPwInput, 'NewPass1234!')
    await userEvent.type(confirmPwInput, 'NewPass1234!')
    await userEvent.click(updatePwBtn)

    await vi.waitFor(() => {
      expect(authClient.updatePassword).toHaveBeenCalledWith('NewPass1234!')
    })
  })

  it('validates PAN format and password confirmation errors', async () => {
    renderWithProviders(<ProfilePage />)

    fireEvent.change(screen.getByPlaceholderText('ABCDE1234F'), { target: { value: 'BADPAN' } })
    fireEvent.click(screen.getByRole('button', { name: /Save PAN/i }))
    expect(await screen.findByText(/does not look like a PAN/i)).toBeInTheDocument()

    const newPwInput = screen.getByLabelText(/^New password/i)
    const confirmPwInput = screen.getByLabelText(/^Confirm password/i)
    fireEvent.change(newPwInput, { target: { value: 'short' } })
    fireEvent.click(screen.getByRole('button', { name: /Update password/i }))
    expect(await screen.findByText(/at least 8 characters/i)).toBeInTheDocument()

    fireEvent.change(newPwInput, { target: { value: 'LongEnough1' } })
    fireEvent.change(confirmPwInput, { target: { value: 'Mismatch123' } })
    fireEvent.click(screen.getByRole('button', { name: /Update password/i }))
    expect(await screen.findByText(/do not match/i)).toBeInTheDocument()
  })

  it('surfaces API errors for name, PAN, and password saves', async () => {
    vi.mocked(apiClient.updateProfile).mockRejectedValueOnce({
      response: { data: { detail: 'Name rejected' } },
    })
    vi.mocked(apiClient.setProfilePan).mockRejectedValueOnce({
      response: { data: { detail: 'PAN rejected' } },
    })
    vi.mocked(authClient.updatePassword).mockRejectedValueOnce(new Error('Password rejected'))

    renderWithProviders(<ProfilePage />)

    fireEvent.change(screen.getByLabelText(/Display name/i), { target: { value: 'X' } })
    fireEvent.click(screen.getByRole('button', { name: /Save name/i }))
    expect(await screen.findByText('Name rejected')).toBeInTheDocument()

    fireEvent.change(screen.getByPlaceholderText('ABCDE1234F'), { target: { value: 'ABCDE1234F' } })
    fireEvent.click(screen.getByRole('button', { name: /Save PAN/i }))
    expect(await screen.findByText('PAN rejected')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText(/^New password/i), { target: { value: 'ValidPass1' } })
    fireEvent.change(screen.getByLabelText(/^Confirm password/i), { target: { value: 'ValidPass1' } })
    fireEvent.click(screen.getByRole('button', { name: /Update password/i }))
    expect(await screen.findByText('Password rejected')).toBeInTheDocument()
  })

  it('toggles password visibility and navigates privacy / back actions', async () => {
    renderWithProviders(<ProfilePage />)

    const newPwInput = screen.getByLabelText(/^New password/i)
    expect(newPwInput).toHaveAttribute('type', 'password')
    const toggles = screen.getAllByRole('button').filter((b) =>
      b.querySelector('[data-testid="VisibilityIcon"]')
    )
    fireEvent.click(toggles[0])
    expect(newPwInput).toHaveAttribute('type', 'text')

    fireEvent.click(screen.getByRole('button', { name: /Open accounts vault/i }))
    fireEvent.click(screen.getByRole('button', { name: /^Back$/i }))
  })

  it('shows Admin role and syncs store-driven name/PAN updates', async () => {
    useAppStore.getState().setIdentity({
      userId: 'u-profile',
      email: 'admin@example.com',
      displayName: 'Admin Person',
      pan: 'ABCDE1234F',
      role: 'admin',
      status: 'active',
    })
    renderWithProviders(<ProfilePage />)
    expect(screen.getByText('Admin')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Admin Person')).toBeInTheDocument()
    expect(screen.getByDisplayValue('ABCDE1234F')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Update PAN/i })).toBeInTheDocument()
  })
})
