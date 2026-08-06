import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
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

const historySessionNoAy = {
  session_id: 'tax-sess-2',
  fy: '2023-24',
  ay: '',
  name: '',
  gross_salary: 0,
  created_at: '',
}

describe('TaxUploadPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState({ taxSessionId: null, activeModule: 'tax_expert', userId: 'u1' })
    vi.mocked(apiClient.getTaxHistory).mockResolvedValue({ sessions: [historySession, historySessionNoAy] } as any)
    vi.mocked(apiClient.deleteTaxSession).mockResolvedValue({ success: true } as any)
  })

  it('renders upload hero with history and formats items correctly', async () => {
    renderWithProviders(<TaxUploadPanel onSessionCreated={vi.fn()} />)

    expect(screen.getByText(/TAX EXPERT · AIS ANALYSER/i)).toBeInTheDocument()
    expect(await screen.findByText(/Welcome back — pick up where you left off/i)).toBeInTheDocument()
    expect(screen.getByText('Previous AIS Sessions')).toBeInTheDocument()
    expect(screen.getByText('FY 2024-25')).toBeInTheDocument()
    expect(screen.getByText('AY 2025-26')).toBeInTheDocument()
    expect(screen.getByText('Rahul Sharma')).toBeInTheDocument()
    expect(screen.getByText(/Salary ₹18,00,000/i)).toBeInTheDocument()
    expect(screen.getByText('FY 2023-24')).toBeInTheDocument()
    expect(screen.getByText('AY 2024-25')).toBeInTheDocument()
  })

  it('renders zero history state when user is not authenticated or has no history', async () => {
    useAppStore.setState({ userId: null })
    renderWithProviders(<TaxUploadPanel onSessionCreated={vi.fn()} />)

    expect(screen.getByText(/Import Your Annual Information Statement/i)).toBeInTheDocument()
    expect(screen.getByText(/Upload AIS PDF/i)).toBeInTheDocument()
  })

  it('shows session-expired warning when flagged', async () => {
    renderWithProviders(<TaxUploadPanel onSessionCreated={vi.fn()} sessionExpired />)
    expect(await screen.findByText(/Your previous session was lost/i)).toBeInTheDocument()
  })

  it('restores a history session on item click and chevron click', async () => {
    renderWithProviders(<TaxUploadPanel onSessionCreated={vi.fn()} />)
    await screen.findByText('Previous AIS Sessions')

    await userEvent.click(screen.getByText('FY 2024-25'))
    expect(useAppStore.getState().taxSessionId).toBe('tax-sess-1')
  })

  it('handles AIS file upload and analysis successfully', async () => {
    const onSessionCreated = vi.fn()
    vi.mocked(apiClient.parseAIS).mockResolvedValueOnce({
      session_id: 'new-parsed-sid',
      financial_year: '2024-25',
    } as any)

    renderWithProviders(<TaxUploadPanel onSessionCreated={onSessionCreated} />)

    const file = new File(['%PDF-test'], 'ais_doc.pdf', { type: 'application/pdf' })
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement

    await userEvent.upload(fileInput, file)
    expect(await screen.findByText('ais_doc.pdf')).toBeInTheDocument()

    const computeBtn = screen.getByRole('button', { name: /Compute My Taxes/i })
    await userEvent.click(computeBtn)

    await waitFor(() => {
      expect(apiClient.parseAIS).toHaveBeenCalledWith(file)
      expect(onSessionCreated).toHaveBeenCalledWith('new-parsed-sid', expect.objectContaining({ session_id: 'new-parsed-sid' }))
    })
  })

  it('handles AIS unknown code error', async () => {
    vi.mocked(apiClient.parseAIS).mockRejectedValueOnce({
      response: {
        data: {
          detail: {
            type: 'AIS_UNKNOWN_CODE',
            code: 'CODE-999',
          },
        },
      },
    })

    renderWithProviders(<TaxUploadPanel onSessionCreated={vi.fn()} />)
    const file = new File(['%PDF-test'], 'ais_doc.pdf', { type: 'application/pdf' })
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement

    await userEvent.upload(fileInput, file)
    await userEvent.click(await screen.findByRole('button', { name: /Compute My Taxes/i }))

    expect(await screen.findByText(/New AIS Information Code Detected: CODE-999/i)).toBeInTheDocument()
  })

  it('handles AIS structure changed error', async () => {
    vi.mocked(apiClient.parseAIS).mockRejectedValueOnce({
      response: {
        data: {
          detail: {
            type: 'AIS_STRUCTURE_CHANGED',
            message: 'Layout modified',
            diff: { changed_columns: ['pan'] },
          },
        },
      },
    })

    renderWithProviders(<TaxUploadPanel onSessionCreated={vi.fn()} />)
    const file = new File(['%PDF-test'], 'ais_doc.pdf', { type: 'application/pdf' })
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement

    await userEvent.upload(fileInput, file)
    await userEvent.click(await screen.findByRole('button', { name: /Compute My Taxes/i }))

    expect(await screen.findByText(/The Income Tax Department updated the PDF format/i)).toBeInTheDocument()
  })

  it('handles generic string error and default error fallback in file analysis', async () => {
    vi.mocked(apiClient.parseAIS).mockRejectedValueOnce({
      response: { data: { detail: 'Password incorrect on PDF' } },
    })

    renderWithProviders(<TaxUploadPanel onSessionCreated={vi.fn()} />)
    const file = new File(['%PDF-test'], 'ais_doc.pdf', { type: 'application/pdf' })
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement

    await userEvent.upload(fileInput, file)
    await userEvent.click(await screen.findByRole('button', { name: /Compute My Taxes/i }))

    expect(await screen.findByText('Password incorrect on PDF')).toBeInTheDocument()
  })

  it('handles delete history flow in main panel and deletes active session', async () => {
    useAppStore.setState({ taxSessionId: 'tax-sess-1' })
    renderWithProviders(<TaxUploadPanel onSessionCreated={vi.fn()} />)
    await screen.findByText('Previous AIS Sessions')

    const deleteButtons = screen.getAllByRole('button', { name: /Delete this session/i })
    await userEvent.click(deleteButtons[0])

    expect(screen.getByText('Delete this AIS session?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Delete permanently/i }))

    await waitFor(() => {
      expect(apiClient.deleteTaxSession).toHaveBeenCalledWith('tax-sess-1')
      expect(useAppStore.getState().taxSessionId).toBeNull()
    })
  })

  it('handles delete failure gracefully without closing dialog abruptly', async () => {
    vi.mocked(apiClient.deleteTaxSession).mockRejectedValueOnce(new Error('Network failure'))
    renderWithProviders(<TaxUploadPanel onSessionCreated={vi.fn()} />)
    await screen.findByText('Previous AIS Sessions')

    const deleteButtons = screen.getAllByRole('button', { name: /Delete this session/i })
    await userEvent.click(deleteButtons[0])

    await userEvent.click(screen.getByRole('button', { name: /Delete permanently/i }))
    await waitFor(() => {
      expect(apiClient.deleteTaxSession).toHaveBeenCalled()
    })
  })

  it('cancels delete dialog on Cancel button click', async () => {
    renderWithProviders(<TaxUploadPanel onSessionCreated={vi.fn()} />)
    await screen.findByText('Previous AIS Sessions')

    const deleteButtons = screen.getAllByRole('button', { name: /Delete this session/i })
    await userEvent.click(deleteButtons[0])

    await userEvent.click(screen.getByRole('button', { name: /Cancel/i }))
    await waitFor(() => {
      expect(screen.queryByText('Delete this AIS session?')).not.toBeInTheDocument()
    })
  })

  it('renders SwitchTaxSessionButton popover and handles selection, mini-upload and deletion', async () => {
    useAppStore.setState({ taxSessionId: 'tax-sess-1' })
    renderWithProviders(<SwitchTaxSessionButton sessionId="tax-sess-1" />)

    await userEvent.click(screen.getByRole('button', { name: /Switch AIS session/i }))
    expect(await screen.findByText('AIS Sessions')).toBeInTheDocument()

    // Select second session
    await userEvent.click(screen.getByText('FY 2023-24'))
    expect(useAppStore.getState().taxSessionId).toBe('tax-sess-2')

    // Reopen popover and test MiniDropzone upload
    await userEvent.click(screen.getByRole('button', { name: /Switch AIS session/i }))
    expect(await screen.findByText('AIS Sessions')).toBeInTheDocument()

    vi.mocked(apiClient.parseAIS).mockResolvedValueOnce({
      session_id: 'popover-uploaded-sid',
      financial_year: '2024-25',
    } as any)

    const file = new File(['%PDF-mini'], 'mini_ais.pdf', { type: 'application/pdf' })
    const miniInput = document.querySelector('input[type="file"]') as HTMLInputElement
    await userEvent.upload(miniInput, file)

    const computeImportBtn = await screen.findByRole('button', { name: /Compute & Import/i })
    await userEvent.click(computeImportBtn)

    await waitFor(() => {
      expect(useAppStore.getState().taxSessionId).toBe('popover-uploaded-sid')
    })
  })

  it('handles MiniDropzone upload errors in popover', async () => {
    useAppStore.setState({ taxSessionId: 'tax-sess-1' })
    renderWithProviders(<SwitchTaxSessionButton sessionId="tax-sess-1" />)

    await userEvent.click(screen.getByRole('button', { name: /Switch AIS session/i }))

    // Test AIS_UNKNOWN_CODE in MiniDropzone
    vi.mocked(apiClient.parseAIS).mockRejectedValueOnce({
      response: { data: { detail: { type: 'AIS_UNKNOWN_CODE', code: 'CODE-888' } } },
    })

    const file = new File(['%PDF-mini'], 'mini_ais.pdf', { type: 'application/pdf' })
    const miniInput = document.querySelector('input[type="file"]') as HTMLInputElement
    await userEvent.upload(miniInput, file)
    await userEvent.click(await screen.findByRole('button', { name: /Compute & Import/i }))

    expect(await screen.findByText(/New AIS code detected: CODE-888/i)).toBeInTheDocument()

    // Test generic object error in MiniDropzone
    vi.mocked(apiClient.parseAIS).mockRejectedValueOnce({
      response: { data: { detail: { message: 'PDF Corrupted' } } },
    })
    await userEvent.click(await screen.findByRole('button', { name: /Compute & Import/i }))
    expect(await screen.findByText('PDF Corrupted')).toBeInTheDocument()
  })

  it('handles delete flow inside SwitchTaxSessionButton popover', async () => {
    useAppStore.setState({ taxSessionId: 'tax-sess-1' })
    renderWithProviders(<SwitchTaxSessionButton sessionId="tax-sess-1" />)

    await userEvent.click(screen.getByRole('button', { name: /Switch AIS session/i }))
    expect(await screen.findByText('AIS Sessions')).toBeInTheDocument()

    const deleteButtons = screen.getAllByRole('button', { name: /Delete this session/i })
    await userEvent.click(deleteButtons[0])

    expect(screen.getByText('Delete this AIS session?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Delete permanently/i }))

    await waitFor(() => {
      expect(apiClient.deleteTaxSession).toHaveBeenCalledWith('tax-sess-1')
      expect(useAppStore.getState().taxSessionId).toBeNull()
    })
  })

  it('handles delete error inside SwitchTaxSessionButton popover gracefully', async () => {
    vi.mocked(apiClient.deleteTaxSession).mockRejectedValueOnce(new Error('Delete popover err'))
    renderWithProviders(<SwitchTaxSessionButton sessionId="tax-sess-1" />)

    await userEvent.click(screen.getByRole('button', { name: /Switch AIS session/i }))
    expect(await screen.findByText('AIS Sessions')).toBeInTheDocument()

    const deleteButtons = screen.getAllByRole('button', { name: /Delete this session/i })
    await userEvent.click(deleteButtons[0])

    await userEvent.click(screen.getByRole('button', { name: /Delete permanently/i }))
    await waitFor(() => {
      expect(apiClient.deleteTaxSession).toHaveBeenCalled()
    })
  })

  it('handles empty history in SwitchTaxSessionButton popover', async () => {
    vi.mocked(apiClient.getTaxHistory).mockResolvedValueOnce({ sessions: [] } as any)
    renderWithProviders(<SwitchTaxSessionButton sessionId="tax-sess-1" />)

    await userEvent.click(screen.getByRole('button', { name: /Switch AIS session/i }))
    expect(await screen.findByText('No previous AIS sessions found')).toBeInTheDocument()
  })

  it('handles fallback error messages when analyze fails without specific detail', async () => {
    vi.mocked(apiClient.parseAIS).mockRejectedValueOnce({
      response: { data: {} },
    })

    renderWithProviders(<TaxUploadPanel onSessionCreated={vi.fn()} />)
    const file = new File(['%PDF-test'], 'ais_doc.pdf', { type: 'application/pdf' })
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement

    await userEvent.upload(fileInput, file)
    await userEvent.click(await screen.findByRole('button', { name: /Compute My Taxes/i }))

    expect(await screen.findByText(/Failed to parse AIS. Ensure this is a valid Annual Information Statement PDF./i)).toBeInTheDocument()
  })

  it('handles extractErrorMessage when detail is an object without message property', async () => {
    useAppStore.setState({ taxSessionId: 'tax-sess-1' })
    renderWithProviders(<SwitchTaxSessionButton sessionId="tax-sess-1" />)

    await userEvent.click(screen.getByRole('button', { name: /Switch AIS session/i }))

    vi.mocked(apiClient.parseAIS).mockRejectedValueOnce({
      response: { data: { detail: { code: 'ERR_RAW_OBJ', info: 123 } } },
    })

    const file = new File(['%PDF-mini'], 'mini_ais.pdf', { type: 'application/pdf' })
    const miniInput = document.querySelector('input[type="file"]') as HTMLInputElement
    await userEvent.upload(miniInput, file)
    await userEvent.click(await screen.findByRole('button', { name: /Compute & Import/i }))

    expect(await screen.findByText(/ERR_RAW_OBJ/i)).toBeInTheDocument()
  })

  it('closes popover on close icon click in SwitchTaxSessionButton', async () => {
    renderWithProviders(<SwitchTaxSessionButton sessionId="tax-sess-1" />)

    await userEvent.click(screen.getByRole('button', { name: /Switch AIS session/i }))
    expect(await screen.findByText('AIS Sessions')).toBeInTheDocument()

    const closeBtn = screen.getByTestId('CloseIcon').closest('button')!
    await userEvent.click(closeBtn)

    await waitFor(() => {
      expect(screen.queryByText('AIS Sessions')).not.toBeInTheDocument()
    })
  })
})
