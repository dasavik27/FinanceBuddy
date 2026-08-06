import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/utils'
import TaxUploadPanel, { SwitchTaxSessionButton } from './TaxUploadPanel'
import { apiClient } from '../../../shared/api/client'
import { useAppStore } from '../../../shared/store/appStore'

vi.mock('../../../shared/api/client', () => ({
  apiClient: {
    getTaxHistory: vi.fn(),
    parseAIS: vi.fn(),
    deleteTaxSession: vi.fn(),
  },
}))

const historySession = {
  session_id: 'tax-sess-1',
  fy: '2024-25',
  ay: '2025-26',
  name: 'Rahul Sharma',
  gross_salary: 1800000,
  created_at: '2025-01-15T10:00:00.000Z',
}

describe('TaxUploadPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState({ taxSessionId: null, activeModule: 'tax_expert', userId: 'u1' })
    vi.mocked(apiClient.getTaxHistory).mockResolvedValue({ sessions: [historySession] } as any)
  })

  it('renders upload hero with history when prior sessions exist', async () => {
    renderWithProviders(<TaxUploadPanel onSessionCreated={vi.fn()} />)

    expect(screen.getByText(/TAX EXPERT · AIS ANALYSER/i)).toBeInTheDocument()
    expect(await screen.findByText(/Welcome back — pick up where you left off/i)).toBeInTheDocument()
    expect(screen.getByText('Previous AIS Sessions')).toBeInTheDocument()
    expect(screen.getByText('FY 2024-25')).toBeInTheDocument()
    expect(screen.getByText('Rahul Sharma')).toBeInTheDocument()
  })

  it('shows session-expired warning when flagged', async () => {
    renderWithProviders(<TaxUploadPanel onSessionCreated={vi.fn()} sessionExpired />)

    expect(await screen.findByText(/Your previous session was lost/i)).toBeInTheDocument()
  })

  it('restores a history session on click', async () => {
    renderWithProviders(<TaxUploadPanel onSessionCreated={vi.fn()} />)
    await screen.findByText('Previous AIS Sessions')

    await userEvent.click(screen.getByText('FY 2024-25'))

    expect(useAppStore.getState().taxSessionId).toBe('tax-sess-1')
  })

  it('opens delete confirmation dialog from history card', async () => {
    renderWithProviders(<TaxUploadPanel onSessionCreated={vi.fn()} />)
    await screen.findByText('Previous AIS Sessions')

    const deleteIcon = await screen.findByTestId('DeleteOutlineIcon')
    fireEvent.click(deleteIcon.closest('button')!)

    expect(await screen.findByText('Delete this AIS session?')).toBeInTheDocument()
  })

  it('SwitchTaxSessionButton opens popover with history', async () => {
    renderWithProviders(<SwitchTaxSessionButton sessionId="tax-sess-1" />)

    await userEvent.click(screen.getByRole('button', { name: /Switch AIS session/i }))

    expect(await screen.findByText('AIS Sessions')).toBeInTheDocument()
    expect(screen.getByText('Import New AIS')).toBeInTheDocument()
  })
})
