import React from 'react'
import { Badge } from '@/components/ui/badge'
import type { RequestStatus } from '@/types'

interface RequestStatusBadgeProps {
  status: RequestStatus
  className?: string
}

const statusConfig: Record<
  RequestStatus,
  { label: string; className: string }
> = {
  new: {
    label: 'New',
    className: 'bg-blue-100 text-blue-800 hover:bg-blue-100 dark:bg-blue-900/30 dark:text-blue-300',
  },
  triaged: {
    label: 'Triaged',
    className: 'bg-purple-100 text-purple-800 hover:bg-purple-100 dark:bg-purple-900/30 dark:text-purple-300',
  },
  assigned: {
    label: 'Assigned',
    className: 'bg-indigo-100 text-indigo-800 hover:bg-indigo-100 dark:bg-indigo-900/30 dark:text-indigo-300',
  },
  in_progress: {
    label: 'In Progress',
    className: 'bg-amber-100 text-amber-800 hover:bg-amber-100 dark:bg-amber-900/30 dark:text-amber-300',
  },
  on_hold: {
    label: 'On Hold',
    className: 'bg-orange-100 text-orange-800 hover:bg-orange-100 dark:bg-orange-900/30 dark:text-orange-300',
  },
  resolved: {
    label: 'Resolved',
    className: 'bg-emerald-100 text-emerald-800 hover:bg-emerald-100 dark:bg-emerald-900/30 dark:text-emerald-300',
  },
  closed: {
    label: 'Closed',
    className: 'bg-slate-100 text-slate-800 hover:bg-slate-100 dark:bg-slate-800 dark:text-slate-300',
  },
  cancelled: {
    label: 'Cancelled',
    className: 'bg-rose-100 text-rose-800 hover:bg-rose-100 dark:bg-rose-900/30 dark:text-rose-300',
  },
}

export function RequestStatusBadge({ status, className }: RequestStatusBadgeProps) {
  const config = statusConfig[status] || {
    label: status,
    className: 'bg-muted text-muted-foreground',
  }

  return (
    <Badge
      variant="outline"
      className={`border-0 font-medium ${config.className} ${className || ''}`}
    >
      {config.label}
    </Badge>
  )
}
