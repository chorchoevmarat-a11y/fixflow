import React from 'react'
import { formatRelativeTime } from '@/lib/utils'
import type { ActivityLog } from '@/types'
import { CircleDot, CheckCircle2, UserPlus, AlertCircle, MessageSquare } from 'lucide-react'

interface ActivityTimelineProps {
  activities: ActivityLog[]
  className?: string
}

function getActivityIcon(action: string) {
  switch (action) {
    case 'created':
    case 'request_created':
      return <CircleDot className="w-4 h-4 text-blue-500" />
    case 'status_changed':
    case 'resolved':
    case 'closed':
      return <CheckCircle2 className="w-4 h-4 text-emerald-500" />
    case 'assigned':
    case 'reassigned':
      return <UserPlus className="w-4 h-4 text-purple-500" />
    case 'note_added':
      return <MessageSquare className="w-4 h-4 text-amber-500" />
    default:
      return <AlertCircle className="w-4 h-4 text-slate-400" />
  }
}

export function ActivityTimeline({ activities, className = '' }: ActivityTimelineProps) {
  if (!activities || activities.length === 0) {
    return (
      <div className="text-center py-6 text-sm text-muted-foreground">
        No activity recorded yet.
      </div>
    )
  }

  return (
    <div className={`relative pl-6 space-y-6 before:absolute before:left-2.5 before:top-2 before:bottom-2 before:w-0.5 before:bg-border ${className}`}>
      {activities.map((act) => (
        <div key={act.id} className="relative flex items-start space-x-3">
          <div className="absolute -left-6 top-0.5 bg-background p-0.5 rounded-full ring-2 ring-background">
            {getActivityIcon(act.action)}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-foreground">
              {act.actor?.full_name || 'System'}
              <span className="text-muted-foreground font-normal ml-1">
                {act.action.replace(/_/g, ' ')}
              </span>
            </div>
            {act.details && Object.keys(act.details).length > 0 && (
              <div className="mt-1 text-xs text-muted-foreground bg-muted/50 rounded p-2 overflow-x-auto">
                <pre className="font-mono text-[11px]">
                  {JSON.stringify(act.details, null, 2)}
                </pre>
              </div>
            )}
            <div className="mt-0.5 text-xs text-muted-foreground">
              {formatRelativeTime(act.created_at)}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
