import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../test/utils'
import PendingAccess from './PendingAccess'
import SuspendedAccess from './SuspendedAccess'
import { useAppStore } from '../store/appStore'
import { apiClient } from '../api/client'

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<any>()
  return {
    ...actual,
    default: actual.default ?? actual.apiClient,
    apiClient: {
      ...actual.apiClient,
      getMe: vi.fn(),
    },
  }
})

describe('Access Status Gate Pages', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    act(() => {
      useAppStore.getState().clearIdentity()
    })
  })

  describe('PendingAccess', () => {
    it('renders pending status card with user email', () => {
      act(() => {
        useAppStore.getState().setIdentity({
          userId: 'u-1',
          email: 'pending.user@example.com',
          status: 'pending',
        })
      })

      renderWithProviders(<PendingAccess />)

      expect(screen.getByText('Access pending')).toBeInTheDocument()
      expect(screen.getByText('pending.user@example.com')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Sign out/i })).toBeInTheDocument()
    })

    it('polls apiClient.getMe and updates identity when approved', async () => {
      act(() => {
        useAppStore.getState().setIdentity({
          userId: 'u-1',
          email: 'pending.user@example.com',
          status: 'pending',
        })
      })

      vi.spyOn(apiClient, 'getMe').mockResolvedValueOnce({
        user_id: 'u-1',
        email: 'pending.user@example.com',
        pan: 'ABCDE1234F',
        display_name: 'Approved User',
        status: 'active',
        role: 'user',
      })

      renderWithProviders(<PendingAccess />)

      await vi.waitFor(() => {
        expect(useAppStore.getState().status).toBe('active')
        expect(useAppStore.getState().pan).toBe('ABCDE1234F')
      })
    })
  })

  describe('SuspendedAccess', () => {
    it('renders suspended message with user email and logout trigger', async () => {
      act(() => {
        useAppStore.getState().setIdentity({
          userId: 'u-revoked',
          email: 'revoked.user@example.com',
          status: 'suspended',
        })
      })

      renderWithProviders(<SuspendedAccess />)

      expect(screen.getByText('Account suspended')).toBeInTheDocument()
      expect(screen.getByText('revoked.user@example.com')).toBeInTheDocument()

      const signOutBtn = screen.getByRole('button', { name: /Sign out/i })
      await userEvent.click(signOutBtn)
    })
  })
})
