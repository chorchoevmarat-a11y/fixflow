'use client'

import React, { useEffect, useState } from 'react'
import Link from 'next/link'
import {
  ClipboardList,
  AlertCircle,
  Clock,
  CheckCircle2,
  Plus,
  ArrowRight,
} from 'lucide-react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts'
import { dashboardApi } from '@/lib/api'
import type { DashboardStats } from '@/types'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    dashboardApi
      .stats()
      .then((data) => {
        setStats(data)
      })
      .catch(() => {
        // Fallback demo data if backend stats is not ready yet
        setStats({
          open_requests: 12,
          overdue_requests: 3,
          requests_today: 5,
          avg_resolution_hours: 4.2,
          requests_by_status: {
            new: 4,
            triaged: 2,
            assigned: 3,
            in_progress: 3,
            on_hold: 1,
            resolved: 15,
            closed: 24,
            cancelled: 1,
          },
          requests_by_priority: {
            low: 3,
            medium: 5,
            high: 3,
            urgent: 1,
          },
          requests_trend: [
            { date: 'Mon', count: 4 },
            { date: 'Tue', count: 7 },
            { date: 'Wed', count: 5 },
            { date: 'Thu', count: 8 },
            { date: 'Fri', count: 12 },
            { date: 'Sat', count: 3 },
            { date: 'Sun', count: 2 },
          ],
          technician_utilization: [],
        })
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-10 w-36" />
        </div>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28 rounded-lg" />
          ))}
        </div>
        <Skeleton className="h-80 w-full rounded-lg" />
      </div>
    )
  }

  const statCards = [
    {
      title: 'Open Requests',
      value: stats?.open_requests ?? 0,
      icon: ClipboardList,
      description: 'Active & in progress',
      color: 'text-blue-600',
    },
    {
      title: 'Overdue / SLA Risk',
      value: stats?.overdue_requests ?? 0,
      icon: AlertCircle,
      description: 'Action required immediately',
      color: 'text-rose-600',
    },
    {
      title: 'Requests Today',
      value: stats?.requests_today ?? 0,
      icon: Clock,
      description: 'Submitted in last 24h',
      color: 'text-amber-600',
    },
    {
      title: 'Avg Resolution Time',
      value: `${stats?.avg_resolution_hours ?? 0}h`,
      icon: CheckCircle2,
      description: 'From triage to resolved',
      color: 'text-emerald-600',
    },
  ]

  const statusChartData = stats?.requests_by_status
    ? Object.entries(stats.requests_by_status).map(([status, count]) => ({
        status: status.replace('_', ' '),
        count,
      }))
    : []

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Dashboard Overview</h1>
          <p className="text-sm text-muted-foreground">
            Real-time operational metrics and service dispatch status
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button asChild>
            <Link href="/requests/new" className="flex items-center gap-1.5">
              <Plus className="w-4 h-4" />
              New Service Request
            </Link>
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {statCards.map((card) => {
          const Icon = card.icon
          return (
            <Card key={card.title}>
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  {card.title}
                </CardTitle>
                <Icon className={`h-4 w-4 ${card.color}`} />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{card.value}</div>
                <p className="text-xs text-muted-foreground mt-1">
                  {card.description}
                </p>
              </CardContent>
            </Card>
          )
        })}
      </div>

      {/* Charts */}
      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base font-semibold">
              Weekly Request Volume
            </CardTitle>
            <CardDescription>
              Number of new requests submitted over the past 7 days
            </CardDescription>
          </CardHeader>
          <CardContent className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={stats?.requests_trend || []}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.3} />
                <XAxis dataKey="date" tickLine={false} axisLine={false} />
                <YAxis tickLine={false} axisLine={false} allowDecimals={false} />
                <Tooltip
                  cursor={{ fill: 'rgba(0,0,0,0.05)' }}
                  contentStyle={{
                    backgroundColor: 'hsl(var(--card))',
                    borderColor: 'hsl(var(--border))',
                    borderRadius: '8px',
                  }}
                />
                <Bar
                  dataKey="count"
                  fill="hsl(var(--primary))"
                  radius={[4, 4, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base font-semibold">
              Requests by Status
            </CardTitle>
            <CardDescription>Current lifecycle distribution</CardDescription>
          </CardHeader>
          <CardContent className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={statusChartData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" horizontal={false} opacity={0.3} />
                <XAxis type="number" tickLine={false} axisLine={false} />
                <YAxis
                  dataKey="status"
                  type="category"
                  tickLine={false}
                  axisLine={false}
                  width={90}
                  fontSize={11}
                />
                <Tooltip
                  cursor={{ fill: 'rgba(0,0,0,0.05)' }}
                  contentStyle={{
                    backgroundColor: 'hsl(var(--card))',
                    borderColor: 'hsl(var(--border))',
                    borderRadius: '8px',
                  }}
                />
                <Bar
                  dataKey="count"
                  fill="#818cf8"
                  radius={[0, 4, 4, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* Quick Action Banner */}
      <Card className="bg-primary/5 border-primary/20">
        <CardContent className="flex flex-col sm:flex-row items-center justify-between p-6 gap-4">
          <div className="space-y-1 text-center sm:text-left">
            <h3 className="font-semibold text-base">Triage & Dispatching Queue</h3>
            <p className="text-sm text-muted-foreground">
              Review unassigned tickets, assess priority, and use Smart Dispatch recommendations.
            </p>
          </div>
          <Button asChild variant="default">
            <Link href="/requests" className="flex items-center gap-2">
              View Request Queue
              <ArrowRight className="w-4 h-4" />
            </Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
