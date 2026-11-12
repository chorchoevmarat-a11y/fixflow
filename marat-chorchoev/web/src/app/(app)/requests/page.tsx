'use client'

import React, { useState, useEffect } from 'react'
import Link from 'next/link'
import {
  Plus,
  Search,
  Filter,
  ArrowUpDown,
  MoreHorizontal,
} from 'lucide-react'
import { requestsApi } from '@/lib/api'
import type { ServiceRequest, RequestStatus, RequestPriority } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { RequestStatusBadge } from '@/components/request-status-badge'
import { PriorityBadge } from '@/components/priority-badge'
import { SlaIndicator } from '@/components/sla-indicator'
import { formatDate } from '@/lib/utils'

export default function RequestsPage() {
  const [requests, setRequests] = useState<ServiceRequest[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [priorityFilter, setPriorityFilter] = useState<string>('all')
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)

  const fetchRequests = async () => {
    setLoading(true)
    try {
      const filters = {
        search: search.trim() || undefined,
        status: statusFilter !== 'all' ? statusFilter : undefined,
        priority: priorityFilter !== 'all' ? priorityFilter : undefined,
        page,
        per_page: 15,
      }
      const data = await requestsApi.list(filters)
      if (data && Array.isArray(data.items)) {
        setRequests(data.items)
        setTotalPages(data.pages || 1)
      } else if (Array.isArray(data)) {
        setRequests(data)
        setTotalPages(1)
      }
    } catch {
      // Fallback sample requests if backend not active
      setRequests([
        {
          id: '1',
          organization_id: 'org1',
          request_number: 'REQ-1001',
          title: 'AC unit leaking water in Conference Room B',
          description: 'Water leaking onto carpet under air conditioner',
          status: 'new',
          priority: 'high',
          requester_id: 'user1',
          tags: ['hvac', 'leak'],
          attachments: [],
          sla_deadline: new Date(Date.now() + 1000 * 60 * 60 * 4).toISOString(),
          sla_breached: false,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
        {
          id: '2',
          organization_id: 'org1',
          request_number: 'REQ-1002',
          title: 'Main entrance automatic door stuck open',
          description: 'Safety hazard and energy waste',
          status: 'triaged',
          priority: 'urgent',
          requester_id: 'user2',
          tags: ['security', 'doors'],
          attachments: [],
          sla_deadline: new Date(Date.now() + 1000 * 60 * 60 * 2).toISOString(),
          sla_breached: false,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchRequests()
  }, [page, statusFilter, priorityFilter])

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setPage(1)
    fetchRequests()
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Service Requests</h1>
          <p className="text-sm text-muted-foreground">
            Manage, triage, and track all incoming maintenance and service requests
          </p>
        </div>
        <Button asChild>
          <Link href="/requests/new" className="flex items-center gap-1.5">
            <Plus className="w-4 h-4" />
            Create Request
          </Link>
        </Button>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col md:flex-row gap-3">
        <form onSubmit={handleSearchSubmit} className="relative flex-1">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search by title, number, or description..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </form>

        <div className="flex flex-wrap gap-2">
          <Select value={statusFilter} onValueChange={(val) => { setStatusFilter(val); setPage(1); }}>
            <SelectTrigger className="w-[140px]">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Statuses</SelectItem>
              <SelectItem value="new">New</SelectItem>
              <SelectItem value="triaged">Triaged</SelectItem>
              <SelectItem value="assigned">Assigned</SelectItem>
              <SelectItem value="in_progress">In Progress</SelectItem>
              <SelectItem value="resolved">Resolved</SelectItem>
              <SelectItem value="closed">Closed</SelectItem>
            </SelectContent>
          </Select>

          <Select value={priorityFilter} onValueChange={(val) => { setPriorityFilter(val); setPage(1); }}>
            <SelectTrigger className="w-[140px]">
              <SelectValue placeholder="Priority" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Priorities</SelectItem>
              <SelectItem value="urgent">Urgent</SelectItem>
              <SelectItem value="high">High</SelectItem>
              <SelectItem value="medium">Medium</SelectItem>
              <SelectItem value="low">Low</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Table */}
      <div className="rounded-md border bg-background overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[120px]">Request #</TableHead>
              <TableHead>Title</TableHead>
              <TableHead className="w-[120px]">Status</TableHead>
              <TableHead className="w-[110px]">Priority</TableHead>
              <TableHead className="w-[160px]">SLA Status</TableHead>
              <TableHead className="w-[160px]">Date Created</TableHead>
              <TableHead className="w-[100px] text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={7} className="h-32 text-center">
                  <div className="flex items-center justify-center gap-2 text-muted-foreground">
                    <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-primary"></div>
                    Loading requests...
                  </div>
                </TableCell>
              </TableRow>
            ) : requests.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="h-32 text-center text-muted-foreground">
                  No service requests found.
                </TableCell>
              </TableRow>
            ) : (
              requests.map((req) => (
                <TableRow key={req.id} className="hover:bg-muted/50">
                  <TableCell className="font-mono text-xs font-semibold">
                    <Link
                      href={`/requests/${req.id}`}
                      className="text-primary hover:underline"
                    >
                      {req.request_number || req.id.slice(0, 8)}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <Link
                      href={`/requests/${req.id}`}
                      className="font-medium text-foreground hover:underline block truncate max-w-md"
                    >
                      {req.title}
                    </Link>
                    {req.property && (
                      <span className="text-xs text-muted-foreground">
                        {req.property.name}
                      </span>
                    )}
                  </TableCell>
                  <TableCell>
                    <RequestStatusBadge status={req.status as RequestStatus} />
                  </TableCell>
                  <TableCell>
                    <PriorityBadge priority={req.priority as RequestPriority} />
                  </TableCell>
                  <TableCell>
                    <SlaIndicator
                      deadline={req.sla_deadline}
                      breached={req.sla_breached}
                      resolvedAt={req.resolved_at}
                    />
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {formatDate(req.created_at)}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-1">
                      {req.status === 'new' && (
                        <Button variant="outline" size="sm" asChild className="h-7 text-xs">
                          <Link href={`/requests/${req.id}/triage`}>Triage</Link>
                        </Button>
                      )}
                      {(req.status === 'triaged' || req.status === 'new') && (
                        <Button variant="default" size="sm" asChild className="h-7 text-xs">
                          <Link href={`/requests/${req.id}/assign`}>Assign</Link>
                        </Button>
                      )}
                      <Button variant="ghost" size="sm" asChild className="h-7 text-xs">
                        <Link href={`/requests/${req.id}`}>View</Link>
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-xs text-muted-foreground">
            Page {page} of {totalPages}
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
