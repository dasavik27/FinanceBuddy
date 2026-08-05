import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
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
})
