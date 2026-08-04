/**
 * The only module in the app that knows which identity provider we use.
 *
 * Everything else imports `authClient` and sees signIn / signOut / getAccessToken /
 * onAuthStateChange. That boundary is deliberate: the backend verifies any OIDC
 * issuer (a JWKS URL, an issuer and an audience), so swapping provider is a rewrite
 * of this one file rather than a hunt through components for SDK calls.
 *
 * If Supabase is not configured, `isConfigured` is false and the app falls back to
 * the legacy PAN sign-in. That keeps "change the database" and "change how people
 * sign in" independently deployable, and independently revertible.
 */

import { createClient, type Session, type SupabaseClient } from '@supabase/supabase-js'

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL ?? ''
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY ?? ''

/** Same base as shared/api/client.ts — required in prod (Vercel) where /api is not proxied. */
const API_BASE = (import.meta.env.VITE_API_URL || '/api').replace(/\/$/, '')

function backendUrl(path: string): string {
  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`
}

export const isConfigured = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY)

// Not created when unconfigured: createClient throws on an empty URL, which would
// take down the whole bundle at import time rather than degrading to PAN login.
const supabase: SupabaseClient | null = isConfigured
  ? createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        // The provider redirects back with the token in the URL fragment; without
        // this the session is silently dropped on the way home from Google.
        detectSessionInUrl: true,
      },
    })
  : null

/** Soft cache for Bearer tokens — avoid getSession() on every Axios call. */
let _accessTokenCache: { token: string; freshUntilMs: number } | null = null

function _tokenFreshUntilMs(token: string, nowMs: number): number {
  try {
    const payload = token.split('.')[1]
    if (!payload) return nowMs + 30_000
    const json = JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')))
    const expSec = typeof json?.exp === 'number' ? json.exp : 0
    if (!expSec) return nowMs + 30_000
    // Refresh a minute before expiry so we never send a near-dead token.
    return Math.max(nowMs, expSec * 1000 - 60_000)
  } catch {
    return nowMs + 30_000
  }
}

export interface AuthUser {
  id: string
  email: string | null
}

export type AccessRequestStatus = 'none' | 'pending' | 'approved'

/** Structured banner shown on the landing sign-in card. */
export interface AuthBanner {
  title: string
  detail: string
  /** Drives Raise request / Check status actions. */
  access_request_status: AccessRequestStatus | null
  severity: 'info' | 'error'
}

/** Shown when the email has no row in access_requests. */
export const REQUEST_ACCESS_MESSAGE =
  'You do not have access yet. Please submit an access request and wait for an administrator to approve you.'

/** OAuth/sign-up disabled bounce — no Supabase Auth user; guide to request or status check. */
export const OAUTH_NO_ACCOUNT_MESSAGE =
  'No login account yet. Raise an access request, or enter your request email above and tap Check status.'

const OAUTH_ERROR_KEY = 'fb_oauth_error_msg'

export function normalizeAuthMessage(raw: string | null | undefined): string | null {
  if (!raw) return null
  let msg = raw.trim()
  if (!msg) return null

  // Collapse accidental exact duplication (double effect / double URL parse).
  if (msg.length > 40 && msg.length % 2 === 0) {
    const half = msg.length / 2
    if (msg.slice(0, half) === msg.slice(half)) msg = msg.slice(0, half)
  }

  const doubled = OAUTH_NO_ACCOUNT_MESSAGE + OAUTH_NO_ACCOUNT_MESSAGE
  if (msg.includes(doubled)) msg = msg.replace(doubled, OAUTH_NO_ACCOUNT_MESSAGE)

  return msg
}

export function bannerForAccessStatus(
  status: AccessRequestStatus | string | null | undefined,
): AuthBanner {
  if (status === 'pending') {
    return {
      title: 'Request pending',
      detail: 'Your access request is waiting for admin approval. You will get an invite once it is approved.',
      access_request_status: 'pending',
      severity: 'info',
    }
  }
  if (status === 'approved') {
    return {
      title: 'Password not set yet',
      detail:
        'Your access is approved. Open the invite email we sent, create your password there, then sign in here with that password.',
      access_request_status: 'approved',
      severity: 'info',
    }
  }
  return {
    title: 'Access required',
    detail: 'You do not have access yet. Raise a request, or enter your email above and check status if you already submitted one.',
    access_request_status: 'none',
    severity: 'info',
  }
}

export function bannerForOAuthNoAccount(): AuthBanner {
  return {
    title: 'No login account',
    detail: 'Raise an access request if you are new. Already requested? Enter that email above and tap Check status.',
    access_request_status: 'none',
    severity: 'info',
  }
}

export function bannerForError(message: string): AuthBanner {
  return {
    title: 'Sign-in failed',
    detail: normalizeAuthMessage(message) || 'Please try again.',
    access_request_status: null,
    severity: 'error',
  }
}

export function messageForAccessStatus(status: AccessRequestStatus | string | null | undefined): string {
  const banner = bannerForAccessStatus(status)
  return `${banner.title}. ${banner.detail}`
}

/**
 * Map provider / OAuth error text into a clear "request access" message when the
 * failure is "no account / sign-ups disabled / not invited".
 */
export function toAccessRequestMessage(raw: string | null | undefined): string | null {
  if (!raw) return null
  const text = raw.replace(/\+/g, ' ').toLowerCase()
  const hints = [
    'signup',
    'sign up',
    'signups not allowed',
    'not allowed',
    'access_denied',
    'access denied',
    'user not found',
    'invalid login',
    'invalid credentials',
    'email not confirmed',
    'not authorized',
    'not_authorized',
    'disabled',
  ]
  if (hints.some((h) => text.includes(h))) return OAUTH_NO_ACCOUNT_MESSAGE
  return null
}

/**
 * After Google OAuth, Supabase may bounce back with ?error= / #error= when the
 * user has no Auth account (e.g. public sign-up off). Parse and clear the URL.
 */
export function consumeOAuthErrorFromUrl(): string | null {
  if (typeof window === 'undefined') return null

  const fromSearch = new URLSearchParams(window.location.search)
  const hash = window.location.hash.startsWith('#')
    ? window.location.hash.slice(1)
    : window.location.hash
  const fromHash = new URLSearchParams(hash)

  const code = fromSearch.get('error_code') || fromHash.get('error_code')
  const error = fromSearch.get('error') || fromHash.get('error')
  const description =
    fromSearch.get('error_description') || fromHash.get('error_description')

  const url = new URL(window.location.href)
  ;['error', 'error_code', 'error_description'].forEach((k) => url.searchParams.delete(k))
  const hadErrorParams = Boolean(code || error || description)
  if (hadErrorParams) {
    url.hash = ''
    window.history.replaceState({}, '', `${url.pathname}${url.search}`)
  }

  if (!hadErrorParams) return null

  // StrictMode / double mount must not surface the same OAuth copy twice.
  const cached = sessionStorage.getItem(OAUTH_ERROR_KEY)
  if (cached) return cached

  const combined = [code, error, description].filter(Boolean).join(' ')
  const message = normalizeAuthMessage(
    toAccessRequestMessage(combined) || OAUTH_NO_ACCOUNT_MESSAGE,
  )!
  sessionStorage.setItem(OAUTH_ERROR_KEY, message)
  return message
}

export function clearOAuthErrorCache(): void {
  sessionStorage.removeItem(OAUTH_ERROR_KEY)
}

function extractEmail(user: { email?: string | null; user_metadata?: Record<string, unknown>; identities?: Array<{ identity_data?: Record<string, unknown> }> } | null | undefined): string | null {
  if (!user) return null
  if (user.email && String(user.email).trim()) return String(user.email).trim()
  const meta = user.user_metadata
  if (meta && typeof meta.email === 'string' && meta.email.trim()) return meta.email.trim()
  for (const identity of user.identities ?? []) {
    const idEmail = identity?.identity_data?.email
    if (typeof idEmail === 'string' && idEmail.trim()) return idEmail.trim()
  }
  return null
}

function toUser(session: Session | null): AuthUser | null {
  if (!session?.user) return null
  return { id: session.user.id, email: extractEmail(session.user) }
}

export const authClient = {
  isConfigured,

  /** Start the Google redirect flow. Resolves as the browser navigates away. */
  signInWithGoogle: async (hintEmail?: string): Promise<void> => {
    if (!supabase) throw new Error('Sign-in is not configured.')
    const hint = (hintEmail || '').trim()
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: `${window.location.origin}/`,
        ...(hint ? { queryParams: { login_hint: hint } } : {}),
      },
    })
    if (error) throw error
  },

  /** Sign in with Email and Password. */
  signInWithEmail: async (email: string, password: string): Promise<AuthUser> => {
    if (!supabase) throw new Error('Sign-in is not configured.')
    const { data, error } = await supabase.auth.signInWithPassword({ email, password })
    if (error) throw error
    const user = toUser(data.session)
    if (!user) throw new Error('Could not establish session.')
    return user
  },

  /** Look up access_requests status for an email (public). */
  checkAccessStatus: async (email: string): Promise<{
    email: string
    access_request_status: AccessRequestStatus
    message: string
  }> => {
    const res = await fetch(backendUrl('/auth/access-status'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email.trim() }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || 'Could not check access status.')
    }
    return res.json()
  },

  /** Submit an early access request for prospective users */
  submitAccessRequest: async (payload: {
    name: string
    email: string
    investor_type?: string
    notes?: string
  }): Promise<{ status: string; message: string; request_id?: string }> => {
    const res = await fetch(backendUrl('/auth/request-access'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || 'Could not submit access request.')
    }
    return res.json()
  },

  signOut: async (): Promise<void> => {
    _accessTokenCache = null
    if (!supabase) return
    clearPasswordSetupRequired()
    await supabase.auth.signOut()
  },

  /** Set / replace password for the current session (invite or recovery links). */
  updatePassword: async (password: string): Promise<void> => {
    if (!supabase) throw new Error('Sign-in is not configured.')
    const trimmed = password.trim()
    if (trimmed.length < 8) throw new Error('Password must be at least 8 characters.')
    const { error } = await supabase.auth.updateUser({ password: trimmed })
    if (error) throw error
    clearPasswordSetupRequired()
    // updateUser may rotate the session — drop soft-cache and reload once for PAN/API calls.
    _accessTokenCache = null
    const { data } = await supabase.auth.getSession()
    const token = data.session?.access_token ?? null
    if (token) {
      _accessTokenCache = {
        token,
        freshUntilMs: _tokenFreshUntilMs(token, Date.now()),
      }
    }
  },

  /**
   * A valid access token, or null.
   *
   * Soft-cached until ~60s before JWT exp so bursts of API calls (admin console,
   * dashboards) do not each await getSession(). Cleared on signOut.
   */
  getAccessToken: async (): Promise<string | null> => {
    if (!supabase) return null
    const now = Date.now()
    if (_accessTokenCache && _accessTokenCache.freshUntilMs > now) {
      return _accessTokenCache.token
    }
    const { data } = await supabase.auth.getSession()
    const token = data.session?.access_token ?? null
    _accessTokenCache = token
      ? { token, freshUntilMs: _tokenFreshUntilMs(token, now) }
      : null
    return token
  },

  getUser: async (): Promise<AuthUser | null> => {
    if (!supabase) return null
    const { data, error } = await supabase.auth.getUser()
    if (error || !data.user) {
      const { data: sessionData } = await supabase.auth.getSession()
      return toUser(sessionData.session)
    }
    return { id: data.user.id, email: extractEmail(data.user) }
  },

  /**
   * Fires on sign-in, sign-out, and session restore. Returns an unsubscribe function.
   *
   * TOKEN_REFRESHED is ignored so the app does not re-hit `/auth/me` on every
   * background refresh (the Bearer interceptor already refreshes the access token).
   */
  onAuthStateChange: (handler: (user: AuthUser | null) => void): (() => void) => {
    if (!supabase) return () => {}
    // Capture invite/recovery type before the client strips the URL hash.
    consumePasswordSetupIntentFromUrl()
    const { data } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === 'PASSWORD_RECOVERY') markPasswordSetupRequired()
      if (event === 'TOKEN_REFRESHED') return
      handler(toUser(session))
    })
    return () => data.subscription.unsubscribe()
  },
}

const PASSWORD_SETUP_KEY = 'fb_must_set_password'

/** Invite / recovery links land with type=invite|recovery in the hash or query. */
export function consumePasswordSetupIntentFromUrl(): boolean {
  if (typeof window === 'undefined') return false
  const fromSearch = new URLSearchParams(window.location.search)
  const hash = window.location.hash.startsWith('#')
    ? window.location.hash.slice(1)
    : window.location.hash
  const fromHash = new URLSearchParams(hash)
  const type = (fromSearch.get('type') || fromHash.get('type') || '').toLowerCase()
  if (type === 'invite' || type === 'recovery' || type === 'signup') {
    markPasswordSetupRequired()
    return true
  }
  return isPasswordSetupRequired()
}

export function markPasswordSetupRequired(): void {
  sessionStorage.setItem(PASSWORD_SETUP_KEY, '1')
}

export function clearPasswordSetupRequired(): void {
  sessionStorage.removeItem(PASSWORD_SETUP_KEY)
}

export function isPasswordSetupRequired(): boolean {
  return sessionStorage.getItem(PASSWORD_SETUP_KEY) === '1'
}

// Capture invite/recovery type as soon as this module loads, before the Supabase
// client strips tokens from the URL hash.
if (typeof window !== 'undefined' && isConfigured) {
  consumePasswordSetupIntentFromUrl()
}

/** Prefer access_requests lookup over backend deny copy when we know the user's email. */
export async function lookupAccessNotice(email: string | null | undefined): Promise<{
  message: string
  access_request_status: AccessRequestStatus
  email: string | null
}> {
  const trimmed = (email || '').trim()
  if (!trimmed) {
    return { message: REQUEST_ACCESS_MESSAGE, access_request_status: 'none', email: null }
  }
  try {
    const st = await authClient.checkAccessStatus(trimmed)
    return {
      message: st.message,
      access_request_status: st.access_request_status,
      email: trimmed,
    }
  } catch {
    return { message: REQUEST_ACCESS_MESSAGE, access_request_status: 'none', email: trimmed }
  }
}

/** Try several emails (Google vs form vs stored request email) for pending status. */
export async function lookupAccessNoticeForEmails(
  emails: Array<string | null | undefined>,
): Promise<{
  message: string
  access_request_status: AccessRequestStatus
  email: string | null
}> {
  const unique: string[] = []
  const seen = new Set<string>()
  for (const raw of emails) {
    const trimmed = (raw || '').trim()
    if (!trimmed) continue
    const key = trimmed.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    unique.push(trimmed)
  }
  if (unique.length === 0) {
    return { message: REQUEST_ACCESS_MESSAGE, access_request_status: 'none', email: null }
  }
  const results = await Promise.all(unique.map((email) => lookupAccessNotice(email)))
  const hit = results.find((r) => r.access_request_status !== 'none')
  return hit ?? results[results.length - 1]!
}

export default authClient
