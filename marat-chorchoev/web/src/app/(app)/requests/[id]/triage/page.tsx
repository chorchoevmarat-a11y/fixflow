'use client'

import React, { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { ArrowLeft, CheckCircle2 } from 'lucide-react'
import { requestsApi, categoriesApi } from '@/lib/api'
import type { ServiceRequest, Category, RequestPriority } from '@/types'
import { Button } from '@/components/ui/button'
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

export default function TriagePage() {
  const params = useParams()
  const router = useRouter()
  const id = params.id as string

  const [request, setRequest] = useState<ServiceRequest | null>(null)
  const [categories, setCategories] = useState<Category[]>([])
  const [loading, setLoading] = useState(true)

  const [priority, setPriority] = useState<RequestPriority>('medium')
  const [categoryId, setCategoryId] = useState<string>('')
  const [notes, setNotes] = useState<string>('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return

    Promise.all([requestsApi.get(id), categoriesApi.list()])
      .then(([req, cats]) => {
        setRequest(req)
        setPriority(req.priority)
        if (req.category_id) setCategoryId(req.category_id)
        setCategories(cats)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [id])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    setError(null)

    try {
      await requestsApi.triage(id, {
        priority,
        category_id: categoryId || undefined,
        notes: notes.trim() || undefined,
      })
      router.push(`/requests/${id}`)
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail || 'Failed to triage request'
      setError(msg)
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="max-w-2xl mx-auto space-y-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" asChild>
          <Link href={`/requests/${id}`} className="flex items-center gap-1">
            <ArrowLeft className="w-4 h-4" />
            Back to Request
          </Link>
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Triage Service Request</CardTitle>
          <CardDescription>
            Assess urgency, classify category, and set routing parameters
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {request && (
            <div className="rounded-lg bg-muted/50 p-4 space-y-2 text-sm mb-4">
              <div className="font-semibold text-foreground">{request.title}</div>
              <p className="text-muted-foreground whitespace-pre-wrap">{request.description}</p>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label>Assessed Priority *</Label>
              <Select
                value={priority}
                onValueChange={(val: RequestPriority) => setPriority(val)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select priority" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="low">Low (Routine maintenance)</SelectItem>
                  <SelectItem value="medium">Medium (Standard attention)</SelectItem>
                  <SelectItem value="high">High (Needs rapid dispatch)</SelectItem>
                  <SelectItem value="urgent">Urgent (Emergency / Hazard)</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Category Classification</Label>
              <Select
                value={categoryId}
                onValueChange={(val) => setCategoryId(val)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select category" />
                </SelectTrigger>
                <SelectContent>
                  {categories.map((c) => (
                    <SelectItem key={c.id} value={c.id}>
                      {c.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="triage-notes">Triage Notes / Dispatch Strategy</Label>
              <textarea
                id="triage-notes"
                rows={3}
                className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                placeholder="Initial diagnosis, required parts, or safety recommendations..."
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
                <CheckCircle2 className="w-4 h-4 mr-1.5" />
                {submitting ? 'Saving...' : 'Complete Triage'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
