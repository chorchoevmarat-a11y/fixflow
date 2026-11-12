import React from 'react'
import { Badge } from '@/components/ui/badge'
import type { RequestPriority } from '@/types'

interface PriorityBadgeProps {
  priority: RequestPriority
  className?: string
}

const priorityConfig: Record<
  RequestPriority,
  { label: string; className: string }
> = {
  low: {
    label: 'Low',
    className: 'bg-slate-100 text-slate-700 hover:bg-slate-100 dark:bg-slate-800 dark:text-slate-300',
  },
  medium: {
    label: 'Medium',
    className: 'bg-blue-100 text-blue-800 hover:bg-blue-100 dark:bg-blue-900/30 dark:text-blue-300',
  },
  high: {
    label: 'High',
    className: 'bg-orange-100 text-orange-800 hover:bg-orange-100 dark:bg-orange-900/30 dark:text-orange-300',
  },
  urgent: {
    label: 'Urgent',
    className: 'bg-red-100 text-red-800 hover:bg-red-100 dark:bg-red-900/30 dark:text-red-300 font-semibold',
  },
}

export function PriorityBadge({ priority, className }: PriorityBadgeProps) {
  const config = priorityConfig[priority] || {
    label: priority,
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
