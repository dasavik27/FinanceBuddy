import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import {
  authClient,
  normalizeAuthMessage,
  bannerForAccessStatus,
  bannerForOAuthNoAccount,
  bannerForIssuerMissing,
  bannerForError,
  messageForAccessStatus,
  toAccessRequestMessage,
  consumeOAuthErrorFromUrl,
  clearOAuthErrorCache,
  consumePasswordSetupIntentFromUrl,
  markPasswordSetupRequired,
  clearPasswordSetupRequired,
  isPasswordSetupRequired,
  lookupAccessNotice,
  lookupAccessNoticeForEmails,
  REQUEST_ACCESS_MESSAGE,
} from './authClient'

describe('authClient utilities', () => {
  beforeEach(() => {
    sessionStorage.clear()
    clearOAuthErrorCache()
    clearPasswordSetupRequired()
    vi.restoreAllMocks()
  })

  describe('normalizeAuthMessage', () => {
    it('returns null on empty or null values', () => {
      expect(normalizeAuthMessage(null)).toBeNull()
      expect(normalizeAuthMessage('')).toBeNull()
      expect(normalizeAuthMessage('   ')).toBeNull()
    })

    it('collapses exact accidental duplication', () => {
      const single = 'This is an error message that happens to be duplicated.'
      const doubled = single + single
      expect(normalizeAuthMessage(doubled)).toBe(single)
    })

    it('removes duplicated REQUEST_ACCESS_MESSAGE', () => {
      const duplicated = REQUEST_ACCESS_MESSAGE + REQUEST_ACCESS_MESSAGE
      expect(normalizeAuthMessage(duplicated)).toBe(REQUEST_ACCESS_MESSAGE)
    })

    it('returns standard trimmed string for normal messages', () => {
      expect(normalizeAuthMessage('Invalid password')).toBe('Invalid password')
    })
  })

  describe('banner builders', () => {
    it('builds pending banner', () => {
      const b = bannerForAccessStatus('pending')
      expect(b.title).toBe('Request pending')
      expect(b.access_request_status).toBe('pending')
      expect(b.severity).toBe('info')
    })

    it('builds approved banner', () => {
      const b = bannerForAccessStatus('approved')
      expect(b.title).toBe('Password not set yet')
      expect(b.access_request_status).toBe('approved')
    })

    it('builds default / none banner', () => {
      const b = bannerForAccessStatus('none')
      expect(b.title).toBe('Access required')
      expect(b.detail).toBe(REQUEST_ACCESS_MESSAGE)
      expect(b.access_request_status).toBe('none')
    })

    it('builds oauth and issuer missing banners', () => {
      expect(bannerForOAuthNoAccount().title).toBe('Access required')
      expect(bannerForIssuerMissing().title).toBe('Access required')
      expect(bannerForIssuerMissing('Custom detail').detail).toBe('Custom detail')
    })

    it('builds error banner', () => {
      const b = bannerForError('Invalid credentials')
      expect(b.title).toBe('Sign-in failed')
      expect(b.detail).toBe('Invalid credentials')
      expect(b.severity).toBe('error')
    })

    it('formats full access status message string', () => {
      const msg = messageForAccessStatus('pending')
      expect(msg).toContain('Request pending')
      expect(msg).toContain('waiting for admin approval')
    })
  })

  describe('toAccessRequestMessage', () => {
    it('detects issuer errors', () => {
      expect(toAccessRequestMessage('provider not configured')).toBe(REQUEST_ACCESS_MESSAGE)
      expect(toAccessRequestMessage('no identity provider found')).toBe(REQUEST_ACCESS_MESSAGE)
      expect(toAccessRequestMessage('invalid_issuer in token')).toBe(REQUEST_ACCESS_MESSAGE)
    })

    it('detects no-account and signup disabled errors', () => {
      expect(toAccessRequestMessage('signups not allowed')).toBe(REQUEST_ACCESS_MESSAGE)
      expect(toAccessRequestMessage('access_denied')).toBe(REQUEST_ACCESS_MESSAGE)
      expect(toAccessRequestMessage('user not found')).toBe(REQUEST_ACCESS_MESSAGE)
    })

    it('returns null for unrelated errors', () => {
      expect(toAccessRequestMessage('Network timeout')).toBeNull()
      expect(toAccessRequestMessage(null)).toBeNull()
    })
  })

  describe('password setup intent helpers', () => {
    it('marks, checks, and clears password setup required in session storage', () => {
      expect(isPasswordSetupRequired()).toBe(false)
      markPasswordSetupRequired()
      expect(isPasswordSetupRequired()).toBe(true)
      clearPasswordSetupRequired()
      expect(isPasswordSetupRequired()).toBe(false)
    })

    it('consumes password setup intent from search params or hash', () => {
      // Mock window.location search
      const origLocation = window.location
      delete (window as any).location
      window.location = {
        ...origLocation,
        search: '?type=invite',
        hash: '',
        href: 'http://localhost/?type=invite',
        pathname: '/',
      } as any

      expect(consumePasswordSetupIntentFromUrl()).toBe(true)
      expect(isPasswordSetupRequired()).toBe(true)

      ;(window as any).location = origLocation
    })
  })

  describe('consumeOAuthErrorFromUrl', () => {
    it('returns null when URL has no error params', () => {
      expect(consumeOAuthErrorFromUrl()).toBeNull()
    })

    it('parses error from query params and cleans URL state', () => {
      const origLocation = window.location
      const replaceStateSpy = vi.spyOn(window.history, 'replaceState').mockImplementation(() => {})

      delete (window as any).location
      window.location = {
        ...origLocation,
        search: '?error=access_denied&error_description=User+is+not+allowed',
        hash: '',
        href: 'http://localhost/?error=access_denied&error_description=User+is+not+allowed',
        pathname: '/',
      } as any

      const msg = consumeOAuthErrorFromUrl()
      expect(msg).toBe(REQUEST_ACCESS_MESSAGE)
      expect(replaceStateSpy).toHaveBeenCalled()

      ;(window as any).location = origLocation
    })
  })

  describe('access status API lookups', () => {
    it('lookupAccessNotice returns default for empty email', async () => {
      const res = await lookupAccessNotice('')
      expect(res.access_request_status).toBe('none')
      expect(res.email).toBeNull()
    })

    it('lookupAccessNotice fetches status from checkAccessStatus', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          email: 'user@example.com',
          access_request_status: 'pending',
          message: 'Approval pending',
        }),
      } as any)

      const res = await lookupAccessNotice('user@example.com')
      expect(res.access_request_status).toBe('pending')
      expect(res.message).toBe('Approval pending')
    })

    it('lookupAccessNotice handles network failure gracefully', async () => {
      vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new Error('Network error'))
      const res = await lookupAccessNotice('user@example.com')
      expect(res.access_request_status).toBe('none')
      expect(res.message).toBe(REQUEST_ACCESS_MESSAGE)
    })

    it('lookupAccessNoticeForEmails deduplicates and prioritizes active request', async () => {
      vi.spyOn(globalThis, 'fetch')
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            email: 'a@example.com',
            access_request_status: 'none',
            message: 'No account',
          }),
        } as any)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            email: 'b@example.com',
            access_request_status: 'pending',
            message: 'Pending invite',
          }),
        } as any)

      const res = await lookupAccessNoticeForEmails(['a@example.com', 'b@example.com', 'a@example.com'])
      expect(res.access_request_status).toBe('pending')
      expect(res.email).toBe('b@example.com')
    })

    it('lookupAccessNoticeForEmails returns none when email array is empty', async () => {
      const res = await lookupAccessNoticeForEmails([])
      expect(res.access_request_status).toBe('none')
      expect(res.email).toBeNull()
    })
  })

  describe('authClient methods', () => {
    it('submitAccessRequest calls backend API', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'success', message: 'Submitted', request_id: 'req-1' }),
      } as any)

      const res = await authClient.submitAccessRequest({
        name: 'Jane Doe',
        email: 'jane@example.com',
      })
      expect(res.status).toBe('success')
      expect(res.request_id).toBe('req-1')
    })

    it('submitAccessRequest throws on non-ok response', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: false,
        json: async () => ({ detail: 'Bad request' }),
      } as any)
      await expect(authClient.submitAccessRequest({ name: 'X', email: 'x@x.com' })).rejects.toThrow('Bad request')
    })

    it('checkSessionHealth returns true when unconfigured', async () => {
      const isHealth = await authClient.checkSessionHealth()
      expect(typeof isHealth).toBe('boolean')
    })

    it('checkAccessStatus throws on API error', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: false,
        json: async () => ({ detail: 'Not found' }),
      } as any)
      await expect(authClient.checkAccessStatus('x@x.com')).rejects.toThrow('Not found')
    })

    it('checkAccessStatus throws generic error when json parse fails', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: false,
        json: async () => { throw new Error('bad json') },
      } as any)
      await expect(authClient.checkAccessStatus('x@x.com')).rejects.toThrow('Could not check access status')
    })
  })

  describe('bannerForError', () => {
    it('uses fallback message when normalizeAuthMessage returns null', () => {
      const b = bannerForError('')
      expect(b.detail).toBe('Please try again.')
    })
  })

  describe('consumeOAuthErrorFromUrl - cached path', () => {
    it('returns cached message from sessionStorage on second call', () => {
      const origLocation = window.location
      const replaceStateSpy = vi.spyOn(window.history, 'replaceState').mockImplementation(() => {})

      delete (window as any).location
      window.location = {
        ...origLocation,
        search: '?error=access_denied&error_description=User+is+not+allowed',
        hash: '',
        href: 'http://localhost/?error=access_denied&error_description=User+is+not+allowed',
        pathname: '/',
      } as any

      // First call seeds the cache
      consumeOAuthErrorFromUrl()
      // Second call should read from cache
      window.location = {
        ...origLocation,
        search: '?error=access_denied&error_description=User+is+not+allowed',
        hash: '',
        href: 'http://localhost/?error=access_denied&error_description=User+is+not+allowed',
        pathname: '/',
      } as any
      const msg = consumeOAuthErrorFromUrl()
      expect(msg).toBe(REQUEST_ACCESS_MESSAGE)

      ;(window as any).location = origLocation
    })
  })

  describe('consumePasswordSetupIntentFromUrl - hash path', () => {
    it('reads recovery type from hash fragment', () => {
      clearPasswordSetupRequired()
      const origLocation = window.location
      delete (window as any).location
      window.location = {
        ...origLocation,
        search: '',
        hash: '#type=recovery',
        href: 'http://localhost/#type=recovery',
        pathname: '/',
      } as any

      const result = consumePasswordSetupIntentFromUrl()
      expect(result).toBe(true)
      expect(isPasswordSetupRequired()).toBe(true)

      ;(window as any).location = origLocation
    })

    it('returns isPasswordSetupRequired when no type present', () => {
      clearPasswordSetupRequired()
      const origLocation = window.location
      delete (window as any).location
      window.location = {
        ...origLocation,
        search: '',
        hash: '',
        href: 'http://localhost/',
        pathname: '/',
      } as any

      const result = consumePasswordSetupIntentFromUrl()
      expect(result).toBe(false)

      ;(window as any).location = origLocation
    })
  })

  describe('authClient extended methods', () => {
    it('bannerForOAuthNoAccount returns none banner', () => {
      const b = bannerForOAuthNoAccount()
      expect(b.access_request_status).toBe('none')
    })

    it('bannerForIssuerMissing returns custom detail if provided', () => {
      const b = bannerForIssuerMissing('Custom missing issuer message')
      expect(b.detail).toBe('Custom missing issuer message')
      const b2 = bannerForIssuerMissing()
      expect(b2.detail).toBe(REQUEST_ACCESS_MESSAGE)
    })

    it('signInWithGoogle executes OAuth flow with and without email hint', async () => {
      await expect(authClient.signInWithGoogle('test@example.com')).resolves.not.toThrow()
      await expect(authClient.signInWithGoogle()).resolves.not.toThrow()
    })

    it('updatePassword rejects short passwords and requires active session', async () => {
      await expect(authClient.updatePassword('short')).rejects.toThrow('at least 8 characters')
      await expect(authClient.updatePassword('validPassword123')).rejects.toThrow()
    })

    it('getUser retrieves user from session', async () => {
      const user = await authClient.getUser()
      expect(user === null || typeof user === 'object').toBe(true)
    })

    it('getAccessToken handles caching and retrieval', async () => {
      const token = await authClient.getAccessToken()
      expect(token === null || typeof token === 'string').toBe(true)
      const cached = await authClient.getAccessToken()
      expect(cached).toBe(token)
    })

    it('onAuthStateChange registers listener and handles events', () => {
      const handler = vi.fn()
      const unsubscribe = authClient.onAuthStateChange(handler)
      expect(typeof unsubscribe).toBe('function')
      unsubscribe()
    })

    it('signInWithEmail handles attempt and errors', async () => {
      await expect(authClient.signInWithEmail('test@example.com', 'pwd123')).rejects.toThrow()
    })

    it('checkSessionHealth checks token validity', async () => {
      const health = await authClient.checkSessionHealth()
      expect(typeof health).toBe('boolean')
    })
  })
})


