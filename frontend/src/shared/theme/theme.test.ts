import { describe, it, expect } from 'vitest'
import { theme, palette, monoFont } from './theme'

describe('theme design system', () => {
  it('has dark mode enabled and correct palette tokens', () => {
    expect(theme.palette.mode).toBe('dark')
    expect(palette.primary).toBe('#6366F1')
    expect(palette.secondary).toBe('#4EDE93')
    expect(palette.tertiary).toBe('#FF516A')
    expect(palette.background).toBe('#0B1326')
    expect(palette.surface).toBe('#131B2E')
  })

  it('configures typography hierarchy with Plus Jakarta Sans and mono font', () => {
    expect(theme.typography.fontFamily).toContain('Plus Jakarta Sans')
    expect(monoFont).toContain('DM Mono')
    expect(theme.typography.h1.fontWeight).toBe(800)
    expect(theme.typography.button.textTransform).toBe('none')
  })

  it('configures component overrides for MuiButton, MuiCard, and MuiTabs', () => {
    expect(theme.components?.MuiButton).toBeDefined()
    expect(theme.components?.MuiCard).toBeDefined()
    expect(theme.components?.MuiTabs).toBeDefined()
    expect(theme.shape.borderRadius).toBe(16)
  })
})
