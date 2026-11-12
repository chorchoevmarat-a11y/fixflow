'use client'

import { useState, useCallback, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { authApi } from '@/lib/api'
import { setToken, getToken, clearAuth, setOrgId, getOrgId } from '@/lib/auth'
import type { User, Organization } from '@/types'

interface AuthState {
  user: User | null
  orgId: string | null
  isLoading: boolean
  isAuthenticated: boolean
}

export function useAuth() {
  const router = useRouter()
  const [state, setState] = useState<AuthState>({
    user: null,
    orgId: getOrgId(),
    isLoading: true,
    isAuthenticated: false,
  })

  const loadUser = useCallback(async () => {
    const token = getToken()
    if (!token) {
      setState((s) => ({ ...s, isLoading: false, isAuthenticated: false }))
      return
    }
    try {
      const user = await authApi.me()
      setState((s) => ({
        ...s,
        user,
        isLoading: false,
        isAuthenticated: true,
      }))
    } catch {
      clearAuth()
      setState((s) => ({
        ...s,
        isLoading: false,
        isAuthenticated: false,
        user: null,
      }))
    }
  }, [])

  useEffect(() => {
    void loadUser()
  }, [loadUser])

  const login = useCallback(
    async (email: string, password: string): Promise<Organization[]> => {
      const tokenData = await authApi.login(email, password)
      setToken(tokenData.access_token)
      const [user, orgs] = await Promise.all([
        authApi.me(),
        authApi.myOrganizations(),
      ])
      setState((s) => ({ ...s, user, isAuthenticated: true }))
      return orgs
    },
    [],
  )

  const selectOrg = useCallback(
    (orgId: string) => {
      setOrgId(orgId)
      setState((s) => ({ ...s, orgId }))
      router.push('/dashboard')
    },
    [router],
  )

  const logout = useCallback(async () => {
    try {
      await authApi.logout()
    } catch {
      // ignore
    } finally {
      clearAuth()
      setState({
        user: null,
        orgId: null,
        isLoading: false,
        isAuthenticated: false,
      })
      router.push('/login')
    }
  }, [router])

  return {
    user: state.user,
    orgId: state.orgId,
    isLoading: state.isLoading,
    isAuthenticated: state.isAuthenticated,
    login,
    selectOrg,
    logout,
    reload: loadUser,
  }
}
