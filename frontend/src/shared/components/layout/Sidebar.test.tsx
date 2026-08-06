import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/utils'
import { Sidebar } from './Sidebar'
import { useAppStore } from '../../store/appStore'

describe('Sidebar', () => {
  const onClose = vi.fn()
  const onToggle = vi.fn()
  const onExpand = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    act(() => {
      useAppStore.getState().setIdentity({
        userId: 'u-sidebar',
        email: 'nav@test.com',
        displayName: 'Nav User',
        pan: 'ABCDE1234F',
        role: 'user',
        status: 'active',
      })
      useAppStore.setState({ activeModule: 'mutual_funds' })
    })
  })

  function renderSidebar(overrides: Partial<Parameters<typeof Sidebar>[0]> = {}) {
    return renderWithProviders(
      <Sidebar
        open={false}
        onClose={onClose}
        isPartial={false}
        collapsed={false}
        onToggle={onToggle}
        onExpand={onExpand}
        {...overrides}
      />,
      { initialEntries: ['/mutual-funds'] }
    )
  }

  it('renders brand and domain navigation links', () => {
    renderSidebar()

    expect(screen.getByText(/Finance/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Mutual Funds/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Indian Stocks/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Tax Expert/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Budget Analyzer/i })).toBeInTheDocument()
  })

  it('calls onToggle when collapse button is clicked', async () => {
    renderSidebar()

    const collapseBtn = screen.getByRole('button', { name: /Collapse sidebar/i })
    await userEvent.click(collapseBtn)

    expect(onToggle).toHaveBeenCalled()
  })

  it('toggles sidebar on Cmd+B keyboard shortcut', () => {
    renderSidebar()

    fireEvent.keyDown(window, { key: 'b', metaKey: true })

    expect(onToggle).toHaveBeenCalled()
  })

  it('shows expand button when collapsed', async () => {
    renderSidebar({ collapsed: true })

    const expandBtn = screen.getByRole('button', { name: /Expand sidebar/i })
    await userEvent.click(expandBtn)

    expect(onToggle).toHaveBeenCalled()
  })

  it('shows signed-in PAN in account status footer', () => {
    renderSidebar()

    expect(screen.getByText('ABCDE1234F')).toBeInTheDocument()
    expect(screen.getByText(/Signed in as/i)).toBeInTheDocument()
  })

  it('renders mobile drawer when open', () => {
    renderSidebar({ open: true })

    expect(screen.getAllByRole('button', { name: /Mutual Funds/i }).length).toBeGreaterThan(0)
  })
})
