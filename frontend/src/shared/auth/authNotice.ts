import type { AccessRequestStatus } from './authClient'
import { clearOAuthErrorCache } from './authClient'

export const AUTH_NOTICE_KEY = 'fb_auth_notice'

export interface AuthNotice {
  message: string
  access_request_status: AccessRequestStatus
  email?: string | null
}

export function readAuthNotice(): AuthNotice | null {
  const raw = sessionStorage.getItem(AUTH_NOTICE_KEY)
  if (!raw) return null
  sessionStorage.removeItem(AUTH_NOTICE_KEY)
  try {
    const parsed = JSON.parse(raw) as AuthNotice
    if (parsed?.message) return parsed
  } catch {
    return { message: raw, access_request_status: 'none' }
  }
  return null
}

export function writeAuthNotice(notice: AuthNotice): void {
  sessionStorage.setItem(AUTH_NOTICE_KEY, JSON.stringify(notice))
}

/** Remember the email used for an access request (Google OAuth may not return a session). */
export const ACCESS_REQUEST_EMAIL_KEY = 'fb_access_request_email'

export function rememberAccessRequestEmail(email: string): void {
  const trimmed = email.trim().toLowerCase()
  if (trimmed) sessionStorage.setItem(ACCESS_REQUEST_EMAIL_KEY, trimmed)
}

export function readAccessRequestEmail(): string | null {
  return sessionStorage.getItem(ACCESS_REQUEST_EMAIL_KEY)
}

export function clearAccessRequestEmail(): void {
  sessionStorage.removeItem(ACCESS_REQUEST_EMAIL_KEY)
}

export function clearAuthLandingCache(): void {
  clearOAuthErrorCache()
  clearAccessRequestEmail()
}
