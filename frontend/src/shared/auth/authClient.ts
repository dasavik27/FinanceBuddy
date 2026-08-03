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

export interface AuthUser {
  id: string
  email: string | null
}

function toUser(session: Session | null): AuthUser | null {
  if (!session?.user) return null
  return { id: session.user.id, email: session.user.email ?? null }
}

export const authClient = {
  isConfigured,

  /** Start the Google redirect flow. Resolves as the browser navigates away. */
  signInWithGoogle: async (): Promise<void> => {
    if (!supabase) throw new Error('Sign-in is not configured.')
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: `${window.location.origin}/dashboard` },
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

  /** Fast 1-click login for local development if dev credentials exist in .env.local */
  signInWithDevAccount: async (): Promise<AuthUser> => {
    if (!supabase) throw new Error('Sign-in is not configured.')
    const email = import.meta.env.VITE_DEV_EMAIL
    const password = import.meta.env.VITE_DEV_PASSWORD
    if (!email || !password) throw new Error('Dev credentials (VITE_DEV_EMAIL, VITE_DEV_PASSWORD) are not set in .env.local')
    return authClient.signInWithEmail(email, password)
  },

  /** Submit an early access request for prospective users */
  submitAccessRequest: async (payload: {
    name: string
    email: string
    investor_type?: string
    notes?: string
  }): Promise<{ status: string; message: string; request_id?: string }> => {
    const res = await fetch('/api/auth/request-access', {
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
    if (!supabase) return
    await supabase.auth.signOut()
  },

  /**
   * A valid access token, or null.
   *
   * getSession() refreshes when the token is close to expiry, so this is called per
   * request rather than cached - a cached token is the one that expires mid-session
   * and logs the user out for no visible reason.
   */
  getAccessToken: async (): Promise<string | null> => {
    if (!supabase) return null
    const { data } = await supabase.auth.getSession()
    return data.session?.access_token ?? null
  },

  getUser: async (): Promise<AuthUser | null> => {
    if (!supabase) return null
    const { data } = await supabase.auth.getSession()
    return toUser(data.session)
  },

  /** Fires on sign-in, sign-out and token refresh. Returns an unsubscribe function. */
  onAuthStateChange: (handler: (user: AuthUser | null) => void): (() => void) => {
    if (!supabase) return () => {}
    const { data } = supabase.auth.onAuthStateChange((_event, session) => {
      handler(toUser(session))
    })
    return () => data.subscription.unsubscribe()
  },
}

export default authClient
