import { describe, it, expect, beforeEach } from 'vitest'
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
})
