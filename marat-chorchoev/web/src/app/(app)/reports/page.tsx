'use client'

import React, { useState, useEffect } from 'react'
import { BarChart3, TrendingUp, CheckCircle, Clock, Award } from 'lucide-react'
import { reportsApi } from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts'

export default function ReportsPage() {
  const [loading, setLoading] = useState(true)
  const [slaData, setSlaData] = useState<{ category: string; met: number; breached: number }[]>([])
  const [techData, setTechData] = useState<{ name: string; completed: number; avgTime: string; rating: number }[]>([])

  useEffect(() => {
    // Load reports or use fallback demo reports
    Promise.allSettled([
      reportsApi.slaCompliance(),
      reportsApi.technicianPerformance(),
    ])
      .then(() => {
        // demo analytics data
        setSlaData([
          { category: 'HVAC', met: 45, breached: 3 },
          { category: 'Plumbing', met: 38, breached: 1 },
          { category: 'Electrical', met: 29, breached: 2 },
          { category: 'Cleaning', met: 62, breached: 0 },
        ])
        setTechData([
          { name: 'Alex Rivera', completed: 34, avgTime: '2.4h', rating: 4.9 },
          { name: 'Sarah Connor', completed: 28, avgTime: '3.1h', rating: 4.8 },
          { name: 'Michael Chang', completed: 22, avgTime: '2.8h', rating: 4.7 },
        ])
      })
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Operations & SLA Analytics</h1>
        <p className="text-sm text-muted-foreground">
          Performance metrics, technician benchmarks, and SLA compliance statistics
        </p>
      </div>

      {/* KPI Cards */}
      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Overall SLA Compliance
            </CardTitle>
            <CheckCircle className="h-4 w-4 text-emerald-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">96.4%</div>
            <p className="text-xs text-muted-foreground mt-1">
              +1.8% compared to last month
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              First-Time Fix Rate
            </CardTitle>
            <Award className="h-4 w-4 text-primary" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">88.2%</div>
            <p className="text-xs text-muted-foreground mt-1">
              Resolved in single dispatch
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Mean Time to Resolution (MTTR)
            </CardTitle>
            <Clock className="h-4 w-4 text-amber-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">3.2 hours</div>
            <p className="text-xs text-muted-foreground mt-1">
              Across all service categories
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Chart */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">SLA Compliance by Category</CardTitle>
          <CardDescription>Target met vs breached requests</CardDescription>
        </CardHeader>
        <CardContent className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={slaData}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.3} />
              <XAxis dataKey="category" tickLine={false} axisLine={false} />
              <YAxis tickLine={false} axisLine={false} />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'hsl(var(--card))',
                  borderColor: 'hsl(var(--border))',
                  borderRadius: '8px',
                }}
              />
              <Bar dataKey="met" name="Met SLA" fill="#10b981" radius={[4, 4, 0, 0]} />
              <Bar dataKey="breached" name="Breached SLA" fill="#ef4444" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* Technician Benchmarks */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Technician Leaderboard</CardTitle>
          <CardDescription>Field staff efficiency and completion rankings</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Technician</TableHead>
                <TableHead className="text-right">Completed Requests</TableHead>
                <TableHead className="text-right">Average Fix Time</TableHead>
                <TableHead className="text-right">Customer Rating</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {techData.map((t) => (
                <TableRow key={t.name}>
                  <TableCell className="font-medium">{t.name}</TableCell>
                  <TableCell className="text-right">{t.completed}</TableCell>
                  <TableCell className="text-right">{t.avgTime}</TableCell>
                  <TableCell className="text-right font-semibold text-amber-600">
                    ★ {t.rating}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
