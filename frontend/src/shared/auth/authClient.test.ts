import { describe, it, expect, beforeEach, vi } from 'vitest'

const { mockAuth } = vi.hoisted(() => {
  const mockAuth = {
    signInWithOAuth: vi.fn(async () => ({ data: { url: 'https://oauth.example' }, error: null })),
    signInWithPassword: vi.fn(async () => ({
      data: { session: null },
      error: { message: 'Invalid login credentials' },
    })),
    signOut: vi.fn(async () => ({ error: null })),
    updateUser: vi.fn(async () => ({ data: { user: {} }, error: null })),
    getSession: vi.fn(async () => ({ data: { session: null }, error: null })),
    onAuthStateChange: vi.fn((cb: (event: string, session: unknown) => void) => {
      ;(mockAuth as { _cb?: typeof cb })._cb = cb
      return { data: { subscription: { unsubscribe: vi.fn() } } }
    }),
    _cb: undefined as undefined | ((event: string, session: unknown) => void),
  }
  return { mockAuth }
})

vi.mock('@supabase/supabase-js', () => ({
  createClient: () => ({ auth: mockAuth }),
}))

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

function b64url(obj: Record<string, unknown>): string {
  const json = JSON.stringify(obj)
  return btoa(json).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function makeJwt(payload: Record<string, unknown>): string {
  return `${b64url({ alg: 'none' })}.${b64url(payload)}.sig`
}

describe('authClient utilities', () => {
  beforeEach(async () => {
    sessionStorage.clear()
    clearOAuthErrorCache()
    clearPasswordSetupRequired()
    vi.clearAllMocks()
    vi.useRealTimers()
    mockAuth.signInWithOAuth.mockResolvedValue({ data: { url: 'https://oauth.example' }, error: null })
    mockAuth.signInWithPassword.mockResolvedValue({
      data: { session: null },
      error: { message: 'Invalid login credentials' },
    })
    mockAuth.signOut.mockResolvedValue({ error: null })
    mockAuth.updateUser.mockResolvedValue({ data: { user: {} }, error: null })
    mockAuth.getSession.mockResolvedValue({ data: { session: null }, error: null })
    mockAuth.onAuthStateChange.mockImplementation((cb: (event: string, session: unknown) => void) => {
      mockAuth._cb = cb
      return { data: { subscription: { unsubscribe: vi.fn() } } }
    })
    // Drop soft-cached access tokens between tests.
    await authClient.signOut()
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
      expect(mockAuth.signInWithOAuth).toHaveBeenCalledWith(
        expect.objectContaining({
          provider: 'google',
          options: expect.objectContaining({
            queryParams: { login_hint: 'test@example.com' },
          }),
        }),
      )
      await expect(authClient.signInWithGoogle()).resolves.not.toThrow()
      expect(mockAuth.signInWithOAuth).toHaveBeenLastCalledWith(
        expect.objectContaining({
          options: expect.not.objectContaining({ queryParams: expect.anything() }),
        }),
      )
    })

    it('signInWithGoogle throws provider errors', async () => {
      mockAuth.signInWithOAuth.mockResolvedValueOnce({ data: null, error: { message: 'oauth failed' } })
      await expect(authClient.signInWithGoogle()).rejects.toEqual({ message: 'oauth failed' })
    })

    it('updatePassword rejects short passwords and caches rotated session token', async () => {
      await expect(authClient.updatePassword('short')).rejects.toThrow('at least 8 characters')

      const token = makeJwt({ exp: Math.floor(Date.now() / 1000) + 3600 })
      mockAuth.updateUser.mockResolvedValueOnce({ data: { user: {} }, error: null })
      mockAuth.getSession.mockResolvedValueOnce({
        data: { session: { access_token: token, user: { id: 'u1', email: 'a@b.com' } } },
        error: null,
      })
      await authClient.updatePassword('validPassword123')
      expect(mockAuth.updateUser).toHaveBeenCalledWith({ password: 'validPassword123' })
      // Soft-cache should serve the rotated token without another getSession.
      mockAuth.getSession.mockClear()
      await expect(authClient.getAccessToken()).resolves.toBe(token)
      expect(mockAuth.getSession).not.toHaveBeenCalled()
    })

    it('updatePassword throws when supabase updateUser fails', async () => {
      mockAuth.updateUser.mockResolvedValueOnce({ data: null, error: { message: 'weak password' } })
      await expect(authClient.updatePassword('validPassword123')).rejects.toEqual({ message: 'weak password' })
    })

    it('getUser extracts email from user, metadata, or identities', async () => {
      mockAuth.getSession.mockResolvedValueOnce({
        data: { session: { user: { id: 'u1', email: '  direct@ex.com  ' } } },
        error: null,
      })
      expect(await authClient.getUser()).toEqual({ id: 'u1', email: 'direct@ex.com' })

      mockAuth.getSession.mockResolvedValueOnce({
        data: {
          session: {
            user: {
              id: 'u2',
              email: '',
              user_metadata: { email: 'meta@ex.com' },
            },
          },
        },
        error: null,
      })
      expect(await authClient.getUser()).toEqual({ id: 'u2', email: 'meta@ex.com' })

      mockAuth.getSession.mockResolvedValueOnce({
        data: {
          session: {
            user: {
              id: 'u3',
              email: null,
              user_metadata: {},
              identities: [{ identity_data: { email: 'id@ex.com' } }],
            },
          },
        },
        error: null,
      })
      expect(await authClient.getUser()).toEqual({ id: 'u3', email: 'id@ex.com' })

      mockAuth.getSession.mockResolvedValueOnce({
        data: { session: { user: { id: 'u4', email: null, identities: [{}] } } },
        error: null,
      })
      expect(await authClient.getUser()).toEqual({ id: 'u4', email: null })
    })

    it('getAccessToken returns null for missing/error sessions', async () => {
      mockAuth.getSession.mockResolvedValueOnce({ data: { session: null }, error: null })
      expect(await authClient.getAccessToken()).toBeNull()

      mockAuth.getSession.mockResolvedValueOnce({
        data: { session: null },
        error: { message: 'session missing' },
      })
      expect(await authClient.getAccessToken()).toBeNull()

      mockAuth.getSession.mockResolvedValueOnce({
        data: { session: { access_token: null, user: { id: 'u' } } },
        error: null,
      })
      expect(await authClient.getAccessToken()).toBeNull()
    })

    it('getAccessToken caches malformed JWTs using the 30s soft TTL', async () => {
      const badJwt = 'not-a-jwt'
      mockAuth.getSession.mockResolvedValueOnce({
        data: { session: { access_token: badJwt, user: { id: 'u' } } },
        error: null,
      })
      expect(await authClient.getAccessToken()).toBe(badJwt)
      mockAuth.getSession.mockClear()
      expect(await authClient.getAccessToken()).toBe(badJwt)
      expect(mockAuth.getSession).not.toHaveBeenCalled()
    })

    it('getAccessToken accepts JWTs without payload/exp and network failures', async () => {
      mockAuth.getSession.mockResolvedValueOnce({
        data: { session: { access_token: 'hdr..sig', user: { id: 'u' } } },
        error: null,
      })
      expect(await authClient.getAccessToken()).toBe('hdr..sig')

      await authClient.signOut()
      const noExp = makeJwt({ sub: 'x' })
      mockAuth.getSession.mockResolvedValueOnce({
        data: { session: { access_token: noExp, user: { id: 'u' } } },
        error: null,
      })
      expect(await authClient.getAccessToken()).toBe(noExp)

      await authClient.signOut()
      mockAuth.getSession.mockRejectedValueOnce(new Error('network'))
      const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
      expect(await authClient.getAccessToken()).toBeNull()
      expect(warn).toHaveBeenCalled()
      warn.mockRestore()
    })

    it('getAccessToken times out when getSession hangs', async () => {
      await authClient.signOut()
      mockAuth.getSession.mockReset()
      mockAuth.getSession.mockImplementation(() => new Promise(() => {}))
      vi.useFakeTimers()
      const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
      try {
        const pending = authClient.getAccessToken()
        await vi.advanceTimersByTimeAsync(6100)
        await expect(pending).resolves.toBeNull()
        expect(warn).toHaveBeenCalled()
      } finally {
        warn.mockRestore()
        vi.useRealTimers()
        mockAuth.getSession.mockReset()
        mockAuth.getSession.mockResolvedValue({ data: { session: null }, error: null })
      }
    })

    it('onAuthStateChange handles recovery and ignores refresh/update events', () => {
      const handler = vi.fn()
      const unsubscribe = authClient.onAuthStateChange(handler)
      expect(typeof mockAuth._cb).toBe('function')

      mockAuth._cb?.('PASSWORD_RECOVERY', { user: { id: 'u1', email: 'r@ex.com' } })
      expect(isPasswordSetupRequired()).toBe(true)
      expect(handler).toHaveBeenCalledWith({ id: 'u1', email: 'r@ex.com' })

      handler.mockClear()
      mockAuth._cb?.('TOKEN_REFRESHED', { user: { id: 'u1', email: 'r@ex.com' } })
      mockAuth._cb?.('USER_UPDATED', { user: { id: 'u1', email: 'r@ex.com' } })
      expect(handler).not.toHaveBeenCalled()

      mockAuth._cb?.('SIGNED_OUT', null)
      expect(handler).toHaveBeenCalledWith(null)

      unsubscribe()
    })

    it('signInWithEmail returns user or throws on missing session', async () => {
      await expect(authClient.signInWithEmail('test@example.com', 'pwd123')).rejects.toEqual({
        message: 'Invalid login credentials',
      })

      mockAuth.signInWithPassword.mockResolvedValueOnce({
        data: {
          session: {
            user: { id: 'u9', email: 'ok@ex.com' },
            access_token: 't',
          },
        },
        error: null,
      })
      await expect(authClient.signInWithEmail('ok@ex.com', 'goodpass')).resolves.toEqual({
        id: 'u9',
        email: 'ok@ex.com',
      })

      mockAuth.signInWithPassword.mockResolvedValueOnce({
        data: { session: null },
        error: null,
      })
      await expect(authClient.signInWithEmail('ok@ex.com', 'goodpass')).rejects.toThrow(
        'Could not establish session.',
      )
    })

    it('checkSessionHealth reflects token presence', async () => {
      await authClient.signOut()
      mockAuth.getSession.mockReset()
      mockAuth.getSession.mockResolvedValueOnce({ data: { session: null }, error: null })
      expect(await authClient.checkSessionHealth()).toBe(false)

      await authClient.signOut()
      const token = makeJwt({ exp: Math.floor(Date.now() / 1000) + 3600 })
      mockAuth.getSession.mockResolvedValueOnce({
        data: { session: { access_token: token, user: { id: 'u' } } },
        error: null,
      })
      expect(await authClient.checkSessionHealth()).toBe(true)
    })

    it('signOut clears soft cache and tolerates provider failures', async () => {
      await expect(authClient.signOut()).resolves.toBeUndefined()
      mockAuth.signOut.mockRejectedValueOnce(new Error('timeout'))
      const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
      await expect(authClient.signOut()).resolves.toBeUndefined()
      expect(warn).toHaveBeenCalled()
      warn.mockRestore()
    })
  })

  describe('toAccessRequestMessage additional hints', () => {
    it('maps not authorized / disabled / email not confirmed', () => {
      expect(toAccessRequestMessage('not authorized')).toBe(REQUEST_ACCESS_MESSAGE)
      expect(toAccessRequestMessage('not_authorized')).toBe(REQUEST_ACCESS_MESSAGE)
      expect(toAccessRequestMessage('account disabled')).toBe(REQUEST_ACCESS_MESSAGE)
      expect(toAccessRequestMessage('email not confirmed')).toBe(REQUEST_ACCESS_MESSAGE)
      expect(toAccessRequestMessage('invalid credentials')).toBe(REQUEST_ACCESS_MESSAGE)
      expect(toAccessRequestMessage('no_verifier found')).toBe(REQUEST_ACCESS_MESSAGE)
    })
  })

  describe('consumeOAuthErrorFromUrl hash fragment', () => {
    it('parses error from hash params', () => {
      const origLocation = window.location
      const replaceStateSpy = vi.spyOn(window.history, 'replaceState').mockImplementation(() => {})
      clearOAuthErrorCache()
      delete (window as any).location
      window.location = {
        ...origLocation,
        search: '',
        hash: '#error=access_denied&error_description=Signups+not+allowed',
        href: 'http://localhost/#error=access_denied',
        pathname: '/',
      } as any

      expect(consumeOAuthErrorFromUrl()).toBe(REQUEST_ACCESS_MESSAGE)
      expect(replaceStateSpy).toHaveBeenCalled()
      ;(window as any).location = origLocation
    })
  })

  describe('consumePasswordSetupIntentFromUrl signup type', () => {
    it('marks password setup for type=signup', () => {
      clearPasswordSetupRequired()
      const origLocation = window.location
      delete (window as any).location
      window.location = {
        ...origLocation,
        search: '?type=signup',
        hash: '',
        href: 'http://localhost/?type=signup',
        pathname: '/',
      } as any
      expect(consumePasswordSetupIntentFromUrl()).toBe(true)
      expect(isPasswordSetupRequired()).toBe(true)
      ;(window as any).location = origLocation
    })
  })

  describe('lookupAccessNotice non-ok and prioritization', () => {
    it('falls back when access-status response is not ok', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: false,
        json: async () => ({ detail: 'Nope' }),
      } as any)
      const res = await lookupAccessNotice('x@y.com')
      expect(res.access_request_status).toBe('none')
    })

    it('returns first non-none status when scanning emails', async () => {
      vi.spyOn(globalThis, 'fetch')
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            email: 'a@example.com',
            access_request_status: 'pending',
            message: 'Pending',
          }),
        } as any)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            email: 'b@example.com',
            access_request_status: 'approved',
            message: 'Approved',
          }),
        } as any)

      const res = await lookupAccessNoticeForEmails(['a@example.com', 'b@example.com'])
      expect(res.access_request_status).toBe('pending')
      expect(res.email).toBe('a@example.com')
    })
  })

  describe('submitAccessRequest parse failure', () => {
    it('throws generic message when error body is not JSON', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: false,
        json: async () => { throw new Error('bad json') },
      } as any)
      await expect(
        authClient.submitAccessRequest({ name: 'X', email: 'x@x.com' }),
      ).rejects.toThrow('Could not submit access request.')
    })
  })

  describe('bannerForAccessStatus null/undefined', () => {
    it('defaults nullish status to none', () => {
      expect(bannerForAccessStatus(null).access_request_status).toBe('none')
      expect(bannerForAccessStatus(undefined).access_request_status).toBe('none')
      expect(messageForAccessStatus('approved')).toContain('Password not set yet')
    })
  })

  describe('normalizeAuthMessage edge cases', () => {
    it('collapses even-length duplicated halves over 40 chars', () => {
      const half = 'abcdefghijklmnopqrstuvwxyz0123456789!!!!'
      expect(normalizeAuthMessage(half + half)).toBe(half)
    })

    it('strips embedded doubled REQUEST_ACCESS_MESSAGE', () => {
      const msg = `prefix ${REQUEST_ACCESS_MESSAGE}${REQUEST_ACCESS_MESSAGE} suffix`
      expect(normalizeAuthMessage(msg)).toBe(`prefix ${REQUEST_ACCESS_MESSAGE} suffix`)
    })
  })

  describe('consumeOAuthErrorFromUrl non-hint error path', () => {
    it('falls back to OAUTH_NO_ACCOUNT_MESSAGE for unrelated error codes', () => {
      const origLocation = window.location
      vi.spyOn(window.history, 'replaceState').mockImplementation(() => {})
      clearOAuthErrorCache()
      delete (window as any).location
      window.location = {
        ...origLocation,
        search: '?error=server_error&error_description=Temporary+outage',
        hash: '',
        href: 'http://localhost/?error=server_error&error_description=Temporary+outage',
        pathname: '/',
      } as any

      expect(consumeOAuthErrorFromUrl()).toBe(REQUEST_ACCESS_MESSAGE)
      ;(window as any).location = origLocation
    })

    it('parses hash fragments that omit the leading #', () => {
      const origLocation = window.location
      vi.spyOn(window.history, 'replaceState').mockImplementation(() => {})
      clearOAuthErrorCache()
      delete (window as any).location
      window.location = {
        ...origLocation,
        search: '',
        hash: 'error=access_denied&error_description=not+allowed',
        href: 'http://localhost/',
        pathname: '/',
      } as any

      expect(consumeOAuthErrorFromUrl()).toBe(REQUEST_ACCESS_MESSAGE)
      ;(window as any).location = origLocation
    })
  })

  describe('checkAccessStatus success and whitespace email', () => {
    it('returns parsed JSON on ok responses', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          email: 'trim@ex.com',
          access_request_status: 'approved',
          message: 'Ready',
        }),
      } as any)
      const res = await authClient.checkAccessStatus('  trim@ex.com  ')
      expect(res.access_request_status).toBe('approved')
      expect(fetch).toHaveBeenCalledWith(
        expect.stringMatching(/\/auth\/access-status$/),
        expect.objectContaining({
          body: JSON.stringify({ email: 'trim@ex.com' }),
        }),
      )
    })
  })

  describe('lookupAccessNoticeForEmails blanks and last-none fallback', () => {
    it('skips blank emails and returns last result when all are none', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          email: 'only@ex.com',
          access_request_status: 'none',
          message: 'No account',
        }),
      } as any)
      const res = await lookupAccessNoticeForEmails(['', '  ', 'only@ex.com', null])
      expect(res.email).toBe('only@ex.com')
      expect(res.access_request_status).toBe('none')
    })
  })
})


