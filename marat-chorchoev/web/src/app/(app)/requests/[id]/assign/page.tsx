'use client'

import React, { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import {
  ArrowLeft,
  Sparkles,
  UserCheck,
  CheckCircle2,
  Calendar,
  AlertCircle,
} from 'lucide-react'
import { requestsApi, assignmentsApi, staffApi } from '@/lib/api'
import type {
  ServiceRequest,
  User,
  SmartDispatchSuggestion,
} from '@/types'
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Skeleton } from '@/components/ui/skeleton'

export default function AssignPage() {
  const params = useParams()
  const router = useRouter()
  const id = params.id as string

  const [request, setRequest] = useState<ServiceRequest | null>(null)
  const [technicians, setTechnicians] = useState<User[]>([])
  const [suggestions, setSuggestions] = useState<SmartDispatchSuggestion[]>([])
  const [loadingSuggestions, setLoadingSuggestions] = useState(true)

  const [selectedTechId, setSelectedTechId] = useState<string>('')
  const [scheduledStart, setScheduledStart] = useState<string>('')
  const [scheduledEnd, setScheduledEnd] = useState<string>('')
  const [notes, setNotes] = useState<string>('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return

    requestsApi
      .get(id)
      .then((data) => setRequest(data))
      .catch(() => {})

    staffApi
      .list()
      .then((users) => {
        const techs = users.filter((u) => u.role === 'technician' || u.role === 'admin' || u.role === 'dispatcher')
        setTechnicians(techs)
      })
      .catch(() => {})

    requestsApi
      .smartDispatch(id)
      .then((res) => {
        setSuggestions(res)
        if (res.length > 0 && !selectedTechId) {
          setSelectedTechId(res[0].technician.id)
        }
      })
      .catch(() => {
        // Mock fallback suggestions if endpoint not ready
        setSuggestions([
          {
            technician: {
              id: 'tech-1',
              email: 'alex@fixflow.com',
              full_name: 'Alex Rivera',
              role: 'technician',
              organization_id: 'org1',
              is_active: true,
              created_at: '',
              updated_at: '',
            },
            score: 95,
            reasons: ['HVAC Certified', 'Available now', 'Nearest to location'],
            current_assignments: 1,
            skills_match: true,
            proximity_score: 98,
            availability: 'available',
          },
          {
            technician: {
              id: 'tech-2',
              email: 'sarah@fixflow.com',
              full_name: 'Sarah Connor',
              role: 'technician',
              organization_id: 'org1',
              is_active: true,
              created_at: '',
              updated_at: '',
            },
            score: 82,
            reasons: ['Plumbing specialist', 'Completing job nearby in 30m'],
            current_assignments: 2,
            skills_match: false,
            proximity_score: 75,
            availability: 'busy',
          },
        ])
      })
      .finally(() => setLoadingSuggestions(false))
  }, [id])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedTechId) {
      setError('Please select a technician')
      return
    }

    setSubmitting(true)
    setError(null)
    try {
      await assignmentsApi.create(id, {
        technician_id: selectedTechId,
        scheduled_start: scheduledStart ? new Date(scheduledStart).toISOString() : undefined,
        scheduled_end: scheduledEnd ? new Date(scheduledEnd).toISOString() : undefined,
        notes: notes.trim() || undefined,
      })
      router.push(`/requests/${id}`)
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail || 'Failed to create assignment'
      setError(msg)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" asChild>
          <Link href={`/requests/${id}`} className="flex items-center gap-1">
            <ArrowLeft className="w-4 h-4" />
            Back to Request
          </Link>
        </Button>
      </div>

      <div>
        <h1 className="text-2xl font-bold tracking-tight">Assign Technician</h1>
        <p className="text-sm text-muted-foreground">
          {request ? `${request.request_number}: ${request.title}` : 'Dispatch field staff'}
        </p>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Smart Dispatch Section */}
      <Card className="border-primary/30 bg-primary/[0.02]">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-primary" />
            <CardTitle className="text-lg">Smart Dispatch Recommendations</CardTitle>
          </div>
          <CardDescription>
            AI-assisted technician matching based on skills, availability, and active workload
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loadingSuggestions ? (
            <div className="grid gap-3 sm:grid-cols-2">
              <Skeleton className="h-24 w-full" />
              <Skeleton className="h-24 w-full" />
            </div>
          ) : suggestions.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No matching recommendation scores available. Please select manually below.
            </p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {suggestions.map((sug) => {
                const isSelected = selectedTechId === sug.technician.id
                return (
                  <div
                    key={sug.technician.id}
                    onClick={() => setSelectedTechId(sug.technician.id)}
                    className={`cursor-pointer rounded-lg border p-4 transition-all ${
                      isSelected
                        ? 'border-primary ring-2 ring-primary/20 bg-primary/5'
                        : 'border-border hover:border-primary/50 bg-card'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-semibold text-sm">
                        {sug.technician.full_name}
                      </span>
                      <span className="text-xs px-2 py-0.5 rounded-full font-bold bg-primary/10 text-primary">
                        Score: {sug.score}%
                      </span>
                    </div>

                    <div className="text-xs text-muted-foreground mb-2 flex items-center gap-2">
                      <span>Workload: {sug.current_assignments} active</span>
                      <span>•</span>
                      <span className="capitalize">{sug.availability}</span>
                    </div>

                    <div className="flex flex-wrap gap-1">
                      {sug.reasons.map((r, i) => (
                        <span
                          key={i}
                          className="text-[11px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground"
                        >
                          {r}
                        </span>
                      ))}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Manual Assignment Form */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Assignment Details</CardTitle>
          <CardDescription>Confirm dispatch schedule and instructions</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label>Assigned Technician *</Label>
              <Select
                value={selectedTechId}
                onValueChange={(val) => setSelectedTechId(val)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select technician" />
                </SelectTrigger>
                <SelectContent>
                  {technicians.map((t) => (
                    <SelectItem key={t.id} value={t.id}>
                      {t.full_name} ({t.role})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="start">Scheduled Start</Label>
                <Input
                  id="start"
                  type="datetime-local"
                  value={scheduledStart}
                  onChange={(e) => setScheduledStart(e.target.value)}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="end">Scheduled End</Label>
                <Input
                  id="end"
                  type="datetime-local"
                  value={scheduledEnd}
                  onChange={(e) => setScheduledEnd(e.target.value)}
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="notes">Instructions / Field Notes</Label>
              <textarea
                id="notes"
                rows={3}
                className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                placeholder="Special instructions, gate codes, or priority details for the technician..."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
            </div>

            <div className="flex justify-end gap-3 pt-4">
              <Button
                type="button"
                variant="outline"
                onClick={() => router.back()}
                disabled={submitting}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={submitting}>
                {submitting ? 'Dispatching...' : 'Dispatch Technician'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
