// ─── Token management ─────────────────────────────────────────────────────────
// Access token is stored in memory (not localStorage) for security.
// Org ID is stored in localStorage for persistence across tabs.

let _accessToken: string | null = null

export function setToken(token: string): void {
  _accessToken = token
  // Also persist to sessionStorage so page refresh works
  if (typeof window !== 'undefined') {
    sessionStorage.setItem('fixflow_token', token)
  }
}

export function getToken(): string | null {
  if (_accessToken) return _accessToken
  // Restore from sessionStorage on page load
  if (typeof window !== 'undefined') {
    const stored = sessionStorage.getItem('fixflow_token')
    if (stored) {
      _accessToken = stored
      return stored
    }
  }
  return null
}

export function clearToken(): void {
  _accessToken = null
  if (typeof window !== 'undefined') {
    sessionStorage.removeItem('fixflow_token')
  }
}

// ─── Org selection ────────────────────────────────────────────────────────────

export function setOrgId(orgId: string): void {
  if (typeof window !== 'undefined') {
    localStorage.setItem('fixflow_org_id', orgId)
  }
}

export function getOrgId(): string | null {
  if (typeof window !== 'undefined') {
    return localStorage.getItem('fixflow_org_id')
  }
  return null
}

export function clearOrgId(): void {
  if (typeof window !== 'undefined') {
    localStorage.removeItem('fixflow_org_id')
  }
}

// ─── Full auth clear ──────────────────────────────────────────────────────────

export function clearAuth(): void {
  clearToken()
  clearOrgId()
}

// ─── Auth state helpers ───────────────────────────────────────────────────────

export function isAuthenticated(): boolean {
  return getToken() !== null
}
