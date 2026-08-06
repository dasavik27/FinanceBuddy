import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  readAuthNotice,
  writeAuthNotice,
  rememberAccessRequestEmail,
  readAccessRequestEmail,
  clearAccessRequestEmail,
  clearAuthNotice,
  clearAuthLandingCache,
  AUTH_NOTICE_KEY,
  ACCESS_REQUEST_EMAIL_KEY,
} from './authNotice'

vi.mock('./authClient', () => ({
  clearOAuthErrorCache: vi.fn(),
}))

describe('authNotice', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.clearAllMocks()
  })

  it('writes and reads auth notice and automatically removes it on read', () => {
    expect(readAuthNotice()).toBeNull()

    writeAuthNotice({
      message: 'Access pending approval',
      access_request_status: 'pending',
      email: 'user@example.com',
    })

    const notice = readAuthNotice()
    expect(notice).toEqual({
      message: 'Access pending approval',
      access_request_status: 'pending',
      email: 'user@example.com',
    })

    // Second read should be null because it removes upon read
    expect(readAuthNotice()).toBeNull()
  })

  it('handles corrupted JSON in session storage gracefully', () => {
    sessionStorage.setItem(AUTH_NOTICE_KEY, '{invalidJson')
    expect(readAuthNotice()).toBeNull()

    sessionStorage.setItem(AUTH_NOTICE_KEY, JSON.stringify({ message: 'no status' }))
    expect(readAuthNotice()).toBeNull()
  })

  it('remembers, reads, and clears access request email', () => {
    expect(readAccessRequestEmail()).toBeNull()

    rememberAccessRequestEmail('  Test.User@EXAMPLE.com  ')
    expect(readAccessRequestEmail()).toBe('test.user@example.com')

    // Empty email should not overwrite
    rememberAccessRequestEmail('')
    expect(readAccessRequestEmail()).toBe('test.user@example.com')

    clearAccessRequestEmail()
    expect(readAccessRequestEmail()).toBeNull()
  })

  it('clears auth notice and cleans all landing cache', () => {
    writeAuthNotice({ message: 'foo', access_request_status: 'pending' })
    rememberAccessRequestEmail('user@test.com')

    clearAuthNotice()
    expect(sessionStorage.getItem(AUTH_NOTICE_KEY)).toBeNull()

    writeAuthNotice({ message: 'bar', access_request_status: 'none' })
    clearAuthLandingCache()
    expect(sessionStorage.getItem(AUTH_NOTICE_KEY)).toBeNull()
    expect(sessionStorage.getItem(ACCESS_REQUEST_EMAIL_KEY)).toBeNull()
  })
})
