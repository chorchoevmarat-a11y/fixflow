'use client'

import React, { useState, useEffect } from 'react'
import { organizationApi } from '@/lib/api'
import type { Organization } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Alert, AlertDescription } from '@/components/ui/alert'

export default function OrganizationSettingsPage() {
  const [org, setOrg] = useState<Organization | null>(null)
  const [name, setName] = useState('')
  const [slaHours, setSlaHours] = useState(24)
  const [currency, setCurrency] = useState('KGS')
  const [timezone, setTimezone] = useState('Asia/Bishkek')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    organizationApi
      .get()
      .then((data) => {
        setOrg(data)
        setName(data.name)
        if (data.settings) {
          setSlaHours(data.settings.default_sla_hours || 24)
          setCurrency(data.settings.currency || 'KGS')
          setTimezone(data.settings.timezone || 'Asia/Bishkek')
        }
      })
      .catch(() => {
        // demo fallback
        setName('FixFlow Operations Demo')
      })
      .finally(() => setLoading(false))
  }, [])

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setSaved(false)
    try {
      await organizationApi.update({
        name,
        settings: {
          sla_enabled: true,
          default_sla_hours: slaHours,
          currency,
          timezone,
        },
      })
      setSaved(true)
    } catch {
      alert('Failed to update organization settings')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Organization Settings</h1>
        <p className="text-sm text-muted-foreground">
          Configure enterprise parameters, SLA thresholds, and localization
        </p>
      </div>

      {saved && (
        <Alert className="bg-emerald-50 border-emerald-200 text-emerald-800">
          <AlertDescription>Settings updated successfully.</AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Profile & Policies</CardTitle>
          <CardDescription>General settings for this workspace</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSave} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="org-name">Organization Name</Label>
              <Input
                id="org-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="sla-hours">Default SLA (Hours)</Label>
                <Input
                  id="sla-hours"
                  type="number"
                  value={slaHours}
                  onChange={(e) => setSlaHours(parseInt(e.target.value) || 24)}
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="currency">Currency Code</Label>
                <Input
                  id="currency"
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value)}
                  required
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="tz">Timezone</Label>
              <Input
                id="tz"
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                required
              />
            </div>

            <div className="flex justify-end pt-4">
              <Button type="submit" disabled={saving}>
                {saving ? 'Saving...' : 'Save Settings'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
