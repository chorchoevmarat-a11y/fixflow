'use client'

import React, { useEffect, useState } from 'react'
import { Building2 } from 'lucide-react'
import { authApi } from '@/lib/api'
import { getOrgId, setOrgId } from '@/lib/auth'
import type { Organization } from '@/types'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

export function OrgSwitcher() {
  const [organizations, setOrganizations] = useState<Organization[]>([])
  const [currentOrgId, setCurrentOrgId] = useState<string | null>(null)

  useEffect(() => {
    setCurrentOrgId(getOrgId())
    authApi
      .myOrganizations()
      .then((orgs) => {
        setOrganizations(orgs)
        if (orgs.length > 0 && !getOrgId()) {
          setOrgId(orgs[0].id)
          setCurrentOrgId(orgs[0].id)
        }
      })
      .catch(() => {
        // ignore
      })
  }, [])

  const handleOrgChange = (orgId: string) => {
    setOrgId(orgId)
    setCurrentOrgId(orgId)
    window.location.reload()
  }

  if (organizations.length === 0) {
    return null
  }

  return (
    <div className="flex items-center gap-2">
      <Building2 className="w-4 h-4 text-muted-foreground" />
      <Select
        value={currentOrgId || organizations[0]?.id || ''}
        onValueChange={handleOrgChange}
      >
        <SelectTrigger className="w-[180px] h-8 text-xs font-medium">
          <SelectValue placeholder="Select organization" />
        </SelectTrigger>
        <SelectContent>
          {organizations.map((org) => (
            <SelectItem key={org.id} value={org.id} className="text-xs">
              {org.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
