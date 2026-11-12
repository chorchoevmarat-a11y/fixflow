'use client'

import React, { useState, useEffect } from 'react'
import Link from 'next/link'
import {
  Calendar as CalendarIcon,
  Clock,
  User,
  ChevronLeft,
  ChevronRight,
  Plus,
} from 'lucide-react'
import { assignmentsApi } from '@/lib/api'
import type { Assignment } from '@/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { formatDate } from '@/lib/utils'

export default function SchedulePage() {
  const [assignments, setAssignments] = useState<Assignment[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    assignmentsApi
      .myAssignments()
      .then((data) => setAssignments(data))
      .catch(() => {
        // Fallback sample schedule items
        setAssignments([
          {
            id: 'assign-1',
            request_id: '1',
            technician_id: 'tech-1',
            status: 'in_progress',
            scheduled_start: new Date(Date.now() + 1000 * 60 * 60 * 1).toISOString(),
            scheduled_end: new Date(Date.now() + 1000 * 60 * 60 * 3).toISOString(),
            notes: 'Check coolant pressure and condenser coils',
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          },
          {
            id: 'assign-2',
            request_id: '2',
            technician_id: 'tech-2',
            status: 'pending',
            scheduled_start: new Date(Date.now() + 1000 * 60 * 60 * 5).toISOString(),
            scheduled_end: new Date(Date.now() + 1000 * 60 * 60 * 7).toISOString(),
            notes: 'Replace hydraulic closer sensor',
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          },
        ])
      })
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Dispatch Schedule</h1>
          <p className="text-sm text-muted-foreground">
            Calendar view of field technician jobs and maintenance appointments
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm">
            <ChevronLeft className="w-4 h-4 mr-1" />
            Previous
          </Button>
          <Button variant="outline" size="sm">
            Today
          </Button>
          <Button variant="outline" size="sm">
            Next
            <ChevronRight className="w-4 h-4 ml-1" />
          </Button>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        {/* Scheduled List */}
        <div className="md:col-span-2 space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Upcoming Dispatches</CardTitle>
              <CardDescription>Scheduled jobs sorted chronologically</CardDescription>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="py-8 text-center text-sm text-muted-foreground">
                  Loading schedule...
                </div>
              ) : assignments.length === 0 ? (
                <div className="py-8 text-center text-sm text-muted-foreground">
                  No appointments scheduled.
                </div>
              ) : (
                <div className="space-y-3">
                  {assignments.map((item) => (
                    <div
                      key={item.id}
                      className="p-4 rounded-lg border bg-card flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:border-primary/50 transition-colors"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <Link
                            href={`/requests/${item.request_id}`}
                            className="font-semibold text-sm hover:underline text-primary"
                          >
                            Job #{item.id.slice(0, 8)}
                          </Link>
                          <Badge variant="secondary" className="capitalize text-xs">
                            {item.status.replace('_', ' ')}
                          </Badge>
                        </div>
                        {item.notes && (
                          <p className="text-xs text-muted-foreground">{item.notes}</p>
                        )}
                        <div className="flex items-center gap-4 text-xs text-muted-foreground pt-1">
                          <span className="flex items-center gap-1">
                            <Clock className="w-3.5 h-3.5" />
                            {item.scheduled_start ? formatDate(item.scheduled_start) : 'TBD'}
                          </span>
                          <span className="flex items-center gap-1">
                            <User className="w-3.5 h-3.5" />
                            {item.technician?.full_name || 'Assigned Tech'}
                          </span>
                        </div>
                      </div>

                      <Button variant="outline" size="sm" asChild>
                        <Link href={`/requests/${item.request_id}`}>View Job</Link>
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Schedule Sidebar info */}
        <div>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Today&apos;s Highlights</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              <div className="flex justify-between border-b pb-2">
                <span className="text-muted-foreground">Total Dispatches</span>
                <span className="font-semibold">{assignments.length}</span>
              </div>
              <div className="flex justify-between border-b pb-2">
                <span className="text-muted-foreground">Active in Field</span>
                <span className="font-semibold text-amber-600">
                  {assignments.filter((a) => a.status === 'in_progress').length}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Completed</span>
                <span className="font-semibold text-emerald-600">
                  {assignments.filter((a) => a.status === 'completed').length}
                </span>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
