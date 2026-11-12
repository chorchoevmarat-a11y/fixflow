'use client'

import React, { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import {
  ArrowLeft,
  Calendar,
  Building,
  User,
  Tag,
  Paperclip,
  Send,
  CheckCircle,
  XCircle,
  UserCheck,
} from 'lucide-react'
import { requestsApi, assignmentsApi } from '@/lib/api'
import type { ServiceRequest, Note, ActivityLog, Assignment } from '@/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { RequestStatusBadge } from '@/components/request-status-badge'
import { PriorityBadge } from '@/components/priority-badge'
import { SlaIndicator } from '@/components/sla-indicator'
import { ActivityTimeline } from '@/components/activity-timeline'
import { formatDate, formatRelativeTime } from '@/lib/utils'
import { Skeleton } from '@/components/ui/skeleton'

export default function RequestDetailPage() {
  const params = useParams()
  const router = useRouter()
  const id = params.id as string

  const [request, setRequest] = useState<ServiceRequest | null>(null)
  const [notes, setNotes] = useState<Note[]>([])
  const [activities, setActivities] = useState<ActivityLog[]>([])
  const [assignments, setAssignments] = useState<Assignment[]>([])
  const [loading, setLoading] = useState(true)

  const [newNote, setNewNote] = useState('')
  const [isInternal, setIsInternal] = useState(false)
  const [sendingNote, setSendingNote] = useState(false)

  const loadData = async () => {
    try {
      const [reqData, notesData, actData, assignData] = await Promise.allSettled([
        requestsApi.get(id),
        requestsApi.getNotes(id),
        requestsApi.getActivity(id),
        assignmentsApi.list(id),
      ])

      if (reqData.status === 'fulfilled') setRequest(reqData.value)
      if (notesData.status === 'fulfilled') setNotes(notesData.value)
      if (actData.status === 'fulfilled') setActivities(actData.value)
      if (assignData.status === 'fulfilled') setAssignments(assignData.value)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (id) {
      loadData()
    }
  }, [id])

  const handleAddNote = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newNote.trim()) return

    setSendingNote(true)
    try {
      const note = await requestsApi.addNote(id, {
        content: newNote.trim(),
        is_internal: isInternal,
      })
      setNotes((prev) => [...prev, note])
      setNewNote('')
      setIsInternal(false)
    } catch {
      // ignore
    } finally {
      setSendingNote(false)
    }
  }

  const handleClose = async () => {
    const res = prompt('Enter resolution notes:')
    if (res !== null) {
      try {
        await requestsApi.close(id, res)
        loadData()
      } catch {
        alert('Failed to close request')
      }
    }
  }

  const handleCancel = async () => {
    const reason = prompt('Enter cancellation reason:')
    if (reason !== null) {
      try {
        await requestsApi.cancel(id, reason)
        loadData()
      } catch {
        alert('Failed to cancel request')
      }
    }
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  if (!request) {
    return (
      <div className="text-center py-12">
        <h2 className="text-xl font-bold">Request not found</h2>
        <Button className="mt-4" asChild>
          <Link href="/requests">Back to list</Link>
        </Button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" asChild>
            <Link href="/requests">
              <ArrowLeft className="w-4 h-4" />
            </Link>
          </Button>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm font-semibold text-muted-foreground">
                {request.request_number || request.id.slice(0, 8)}
              </span>
              <RequestStatusBadge status={request.status} />
              <PriorityBadge priority={request.priority} />
            </div>
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight mt-1">
              {request.title}
            </h1>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex flex-wrap items-center gap-2">
          {request.status === 'new' && (
            <Button variant="outline" asChild>
              <Link href={`/requests/${id}/triage`}>Triage</Link>
            </Button>
          )}
          {(request.status === 'new' || request.status === 'triaged') && (
            <Button asChild>
              <Link href={`/requests/${id}/assign`} className="flex items-center gap-1.5">
                <UserCheck className="w-4 h-4" />
                Assign Technician
              </Link>
            </Button>
          )}
          {request.status !== 'closed' && request.status !== 'cancelled' && (
            <>
              <Button variant="secondary" onClick={handleClose} className="flex items-center gap-1.5">
                <CheckCircle className="w-4 h-4 text-emerald-600" />
                Mark Resolved
              </Button>
              <Button variant="ghost" onClick={handleCancel} className="text-destructive hover:bg-destructive/10">
                Cancel
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Cols: Tabs Content */}
        <div className="lg:col-span-2 space-y-6">
          <Tabs defaultValue="details">
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="details">Details & Notes</TabsTrigger>
              <TabsTrigger value="assignments">
                Assignments ({assignments.length})
              </TabsTrigger>
              <TabsTrigger value="activity">Activity Log</TabsTrigger>
            </TabsList>

            {/* Details & Notes */}
            <TabsContent value="details" className="space-y-6 mt-4">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Description</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="whitespace-pre-wrap text-sm text-foreground">
                    {request.description}
                  </p>
                </CardContent>
              </Card>

              {/* Notes Section */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Discussion & Work Notes</CardTitle>
                  <CardDescription>
                    Add operational notes or tenant communications
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-3">
                    {notes.length === 0 ? (
                      <p className="text-xs text-muted-foreground italic">
                        No notes added yet.
                      </p>
                    ) : (
                      notes.map((note) => (
                        <div
                          key={note.id}
                          className={`p-3 rounded-lg border text-sm ${
                            note.is_internal
                              ? 'bg-amber-50/50 border-amber-200 dark:bg-amber-950/20 dark:border-amber-900/40'
                              : 'bg-muted/40'
                          }`}
                        >
                          <div className="flex items-center justify-between text-xs mb-1">
                            <span className="font-semibold text-foreground">
                              {note.author?.full_name || 'Staff Member'}
                              {note.is_internal && (
                                <span className="ml-2 px-1.5 py-0.5 rounded text-[10px] bg-amber-200 text-amber-900 font-medium">
                                  Internal Only
                                </span>
                              )}
                            </span>
                            <span className="text-muted-foreground">
                              {formatRelativeTime(note.created_at)}
                            </span>
                          </div>
                          <p className="text-foreground whitespace-pre-wrap">
                            {note.content}
                          </p>
                        </div>
                      ))
                    )}
                  </div>

                  <form onSubmit={handleAddNote} className="space-y-3 pt-3 border-t">
                    <textarea
                      rows={3}
                      className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                      placeholder="Write an update, note, or work comment..."
                      value={newNote}
                      onChange={(e) => setNewNote(e.target.value)}
                    />
                    <div className="flex items-center justify-between">
                      <label className="flex items-center gap-2 text-xs cursor-pointer select-none">
                        <input
                          type="checkbox"
                          checked={isInternal}
                          onChange={(e) => setIsInternal(e.target.checked)}
                          className="rounded border-input text-primary"
                        />
                        Internal note (hide from tenants)
                      </label>
                      <Button type="submit" size="sm" disabled={sendingNote || !newNote.trim()}>
                        <Send className="w-3.5 h-3.5 mr-1" />
                        {sendingNote ? 'Posting...' : 'Post Note'}
                      </Button>
                    </div>
                  </form>
                </CardContent>
              </Card>
            </TabsContent>

            {/* Assignments Tab */}
            <TabsContent value="assignments" className="space-y-4 mt-4">
              <Card>
                <CardHeader className="flex flex-row items-center justify-between">
                  <div>
                    <CardTitle className="text-base">Field Assignments</CardTitle>
                    <CardDescription>
                      Technicians dispatched to this service request
                    </CardDescription>
                  </div>
                  <Button size="sm" asChild>
                    <Link href={`/requests/${id}/assign`}>+ Add Assignment</Link>
                  </Button>
                </CardHeader>
                <CardContent>
                  {assignments.length === 0 ? (
                    <p className="text-sm text-muted-foreground py-4 text-center">
                      No technician has been assigned yet.
                    </p>
                  ) : (
                    <div className="divide-y divide-border">
                      {assignments.map((a) => (
                        <div key={a.id} className="py-3 flex items-center justify-between">
                          <div>
                            <div className="text-sm font-semibold">
                              {a.technician?.full_name || 'Assigned Technician'}
                            </div>
                            <div className="text-xs text-muted-foreground capitalize">
                              Status: {a.status}
                            </div>
                            {a.scheduled_start && (
                              <div className="text-xs text-muted-foreground">
                                Scheduled: {formatDate(a.scheduled_start)}
                              </div>
                            )}
                          </div>
                          <span className="text-xs px-2 py-1 bg-muted rounded font-mono capitalize">
                            {a.status}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            {/* Activity Log Tab */}
            <TabsContent value="activity" className="mt-4">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Audit & Activity Log</CardTitle>
                </CardHeader>
                <CardContent>
                  <ActivityTimeline activities={activities} />
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </div>

        {/* Right 1 Col: Metadata Sidebar */}
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
                Request Info
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              <div>
                <span className="text-xs text-muted-foreground block">SLA Target</span>
                <SlaIndicator
                  deadline={request.sla_deadline}
                  breached={request.sla_breached}
                  resolvedAt={request.resolved_at}
                />
              </div>

              <div>
                <span className="text-xs text-muted-foreground block">Property</span>
                <span className="font-medium">
                  {request.property?.name || 'General Facility'}
                </span>
                {request.unit_number && (
                  <span className="text-xs text-muted-foreground block">
                    Unit: {request.unit_number}
                  </span>
                )}
              </div>

              <div>
                <span className="text-xs text-muted-foreground block">Category</span>
                <span className="font-medium">
                  {request.category?.name || 'Uncategorized'}
                </span>
              </div>

              <div>
                <span className="text-xs text-muted-foreground block">Requester</span>
                <span className="font-medium">
                  {request.requester?.full_name || 'Requester'}
                </span>
                <span className="text-xs text-muted-foreground block">
                  {request.requester?.email}
                </span>
              </div>

              <div>
                <span className="text-xs text-muted-foreground block">Date Created</span>
                <span className="text-xs font-mono">
                  {formatDate(request.created_at)}
                </span>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
