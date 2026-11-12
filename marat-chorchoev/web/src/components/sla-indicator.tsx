import React from 'react'
import { Clock, AlertTriangle, CheckCircle } from 'lucide-react'
import { cn } from '@/lib/utils'

interface SlaIndicatorProps {
  deadline?: string | null
  breached?: boolean
  resolvedAt?: string | null
  className?: string
}

export function SlaIndicator({
  deadline,
  breached,
  resolvedAt,
  className,
}: SlaIndicatorProps) {
  if (!deadline) {
    return (
      <span className={cn('text-xs text-muted-foreground flex items-center gap-1', className)}>
        <Clock className="w-3.5 h-3.5" />
        No SLA
      </span>
    )
  }

  const deadlineDate = new Date(deadline)
  const now = resolvedAt ? new Date(resolvedAt) : new Date()
  const isPast = now.getTime() > deadlineDate.getTime()
  const isBreached = breached ?? isPast

  if (isBreached) {
    return (
      <span
        className={cn(
          'inline-flex items-center gap-1.5 text-xs font-semibold px-2 py-0.5 rounded-full bg-rose-100 text-rose-800 dark:bg-rose-950/40 dark:text-rose-400',
          className
        )}
      >
        <AlertTriangle className="w-3.5 h-3.5" />
        SLA Breached
      </span>
    )
  }

  const diffMs = deadlineDate.getTime() - now.getTime()
  const hoursRemaining = Math.max(0, Math.floor(diffMs / (1000 * 60 * 60)))
  const daysRemaining = Math.floor(hoursRemaining / 24)

  if (resolvedAt) {
    return (
      <span
        className={cn(
          'inline-flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-400',
          className
        )}
      >
        <CheckCircle className="w-3.5 h-3.5" />
        Met SLA
      </span>
    )
  }

  const isWarning = hoursRemaining < 4

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded-full',
        isWarning
          ? 'bg-amber-100 text-amber-800 dark:bg-amber-950/40 dark:text-amber-400'
          : 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
        className
      )}
    >
      <Clock className="w-3.5 h-3.5" />
      {daysRemaining > 0
        ? `${daysRemaining}d ${hoursRemaining % 24}h remaining`
        : `${hoursRemaining}h remaining`}
    </span>
  )
}
