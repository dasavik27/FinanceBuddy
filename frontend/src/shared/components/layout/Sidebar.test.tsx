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

  it('toggles sidebar on Ctrl+B keyboard shortcut', () => {
    renderSidebar()
    fireEvent.keyDown(window, { key: 'B', ctrlKey: true })
    expect(onToggle).toHaveBeenCalled()
  })

  it('navigates when a domain nav item is clicked and closes mobile drawer', async () => {
    renderSidebar({ open: true })
    const equityBtns = screen.getAllByRole('button', { name: /Indian Stocks/i })
    await userEvent.click(equityBtns[equityBtns.length - 1])
    expect(onClose).toHaveBeenCalled()
  })

  it('navigates home when brand link is clicked', async () => {
    renderSidebar({ open: true })
    const brand = screen.getAllByRole('link', { name: /Go to dashboard/i })
    await userEvent.click(brand[brand.length - 1])
    expect(onClose).toHaveBeenCalled()
  })

  it('signs out from expanded footer', async () => {
    const logout = vi.fn().mockResolvedValue(undefined)
    act(() => {
      useAppStore.setState({ logout })
    })
    renderSidebar({ collapsed: false })
    const signOutBtn = screen.getByRole('button', { name: /Sign Out/i })
    await userEvent.click(signOutBtn)
    expect(logout).toHaveBeenCalled()
  })

  it('signs out from collapsed icon and shows Guest when pan missing', async () => {
    const logout = vi.fn().mockResolvedValue(undefined)
    act(() => {
      useAppStore.setState({ logout, pan: null })
    })
    renderSidebar({ collapsed: true })
    expect(screen.getByLabelText(/Account: Guest/i)).toBeInTheDocument()
    await userEvent.click(screen.getByLabelText(/Account: Guest/i))
    expect(logout).toHaveBeenCalled()
  })

  it('marks Dashboard active only on exact /dashboard path', () => {
    renderWithProviders(
      <Sidebar
        open={false}
        onClose={onClose}
        isPartial={false}
        collapsed={false}
        onToggle={onToggle}
        onExpand={onExpand}
      />,
      { initialEntries: ['/dashboard'] }
    )
    expect(screen.getByRole('button', { name: /^Dashboard$/i })).toBeInTheDocument()
  })

  it('marks nested domain routes active and ignores unrelated keydowns', async () => {
    renderWithProviders(
      <Sidebar
        open={false}
        onClose={onClose}
        isPartial={true}
        collapsed={false}
        onToggle={onToggle}
        onExpand={onExpand}
      />,
      { initialEntries: ['/mutual-funds/compare'] },
    )
    expect(screen.getByRole('button', { name: /Mutual Funds/i })).toBeInTheDocument()

    fireEvent.keyDown(window, { key: 'b' })
    expect(onToggle).not.toHaveBeenCalled()
    fireEvent.keyDown(window, { key: 'k', metaKey: true })
    expect(onToggle).not.toHaveBeenCalled()

    await userEvent.click(screen.getByRole('button', { name: /Tax Expert/i }))
    expect(onClose).toHaveBeenCalled()
  })

  it('navigates Budget and Equity domains from collapsed rail', async () => {
    renderSidebar({ collapsed: true })
    await userEvent.click(screen.getByRole('button', { name: /Budget Analyzer/i }))
    expect(onClose).toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: /Indian Stocks/i }))
    expect(onClose).toHaveBeenCalledTimes(2)
  })
})
