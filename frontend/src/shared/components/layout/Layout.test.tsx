import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, fireEvent, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/utils'
import Layout from './Layout'
import { useAppStore } from '../../store/appStore'
import React from 'react'

describe('Layout and Sidebar Components', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('finance_buddy_sidebar_collapsed', 'false')
    act(() => {
      useAppStore.getState().setIdentity({
        userId: 'u-layout',
        email: 'user@test.com',
        displayName: 'Test User',
        pan: 'ABCDE1234F',
        role: 'user',
        status: 'active',
      })
    })
  })

  it('renders children content inside Layout shell', () => {
    renderWithProviders(
      <Layout>
        <div data-testid="page-content">Hello FinanceBuddy</div>
      </Layout>
    )

    expect(screen.getByTestId('page-content')).toBeInTheDocument()
    expect(screen.getByText('Hello FinanceBuddy')).toBeInTheDocument()
  })

  it('toggles sidebar collapse with Cmd+B shortcut', () => {
    renderWithProviders(
      <Layout>
        <div>Content</div>
      </Layout>
    )

    // Trigger keyboard shortcut Cmd+B
    fireEvent.keyDown(window, { key: 'b', metaKey: true })
  })

  it('renders navigation links for all financial domains', () => {
    renderWithProviders(
      <Layout>
        <div>Dashboard Overview</div>
      </Layout>
    )

    expect(screen.getByRole('button', { name: /Mutual Funds/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Indian Stocks/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Tax Expert/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Budget Analyzer/i })).toBeInTheDocument()
  })

  it('persists sidebar collapse toggle to localStorage', async () => {
    renderWithProviders(
      <Layout>
        <div>Content</div>
      </Layout>
    )
    const collapseBtn = screen.getByRole('button', { name: /Collapse sidebar/i })
    await userEvent.click(collapseBtn)
    expect(localStorage.getItem('finance_buddy_sidebar_collapsed')).toBe('true')
  })

  it('defaults collapsed when localStorage flag is true', () => {
    localStorage.setItem('finance_buddy_sidebar_collapsed', 'true')
    renderWithProviders(
      <Layout>
        <div>Content</div>
      </Layout>
    )
    expect(screen.getByRole('button', { name: /Expand sidebar/i })).toBeInTheDocument()
  })

  it('opens mobile sidebar from topbar menu button and closes via drawer', async () => {
    renderWithProviders(
      <Layout>
        <div>Content</div>
      </Layout>
    )
    const menuBtns = screen.getAllByRole('button')
    // First toolbar button is the hamburger (md:none still present in DOM)
    await userEvent.click(menuBtns[0])
    expect(screen.getAllByRole('button', { name: /Mutual Funds/i }).length).toBeGreaterThan(0)
    // MUI temporary Drawer backdrop / Escape invokes Layout onClose
    await userEvent.keyboard('{Escape}')
  })

  it('survives localStorage.setItem failures during toggle', async () => {
    const original = window.localStorage.setItem.bind(window.localStorage)
    window.localStorage.setItem = () => {
      throw new Error('quota')
    }
    renderWithProviders(
      <Layout>
        <div>Content</div>
      </Layout>
    )
    fireEvent.keyDown(window, { key: 'b', metaKey: true })
    window.localStorage.setItem = original
  })

  it('defaults collapsed when localStorage.getItem throws', () => {
    const original = window.localStorage.getItem.bind(window.localStorage)
    window.localStorage.getItem = () => {
      throw new Error('blocked')
    }
    renderWithProviders(
      <Layout>
        <div>Content</div>
      </Layout>
    )
    expect(screen.getByRole('button', { name: /Expand sidebar/i })).toBeInTheDocument()
    window.localStorage.getItem = original
  })
})
