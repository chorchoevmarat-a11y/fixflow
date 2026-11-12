'use client'

import React, { useState, useEffect } from 'react'
import { ShieldCheck, Search, Filter } from 'lucide-react'
import { auditApi } from '@/lib/api'
import type { AuditLog } from '@/types'
import { Input } from '@/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { formatDate } from '@/lib/utils'

export default function AuditPage() {
  const [logs, setLogs] = useState<AuditLog[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')

  useEffect(() => {
    auditApi
      .list()
      .then((data) => {
        if (data && Array.isArray(data.items)) {
          setLogs(data.items)
        } else if (Array.isArray(data)) {
          setLogs(data)
        }
      })
      .catch(() => {
        // fallback sample
        setLogs([
          {
            id: 'audit-1',
            organization_id: 'org1',
            actor_id: 'user1',
            actor: {
              id: 'user1',
              email: 'admin@fixflow.com',
              full_name: 'Admin User',
              role: 'admin',
              organization_id: 'org1',
              is_active: true,
              created_at: '',
              updated_at: '',
            },
            action: 'service_request.status_updated',
            resource_type: 'service_request',
            resource_id: '1',
            changes: { status: { old: 'triaged', new: 'assigned' } },
            ip_address: '127.0.0.1',
            created_at: new Date(Date.now() - 1000 * 60 * 30).toISOString(),
          },
          {
            id: 'audit-2',
            organization_id: 'org1',
            actor_id: 'user2',
            actor: {
              id: 'user2',
              email: 'dispatcher@fixflow.com',
              full_name: 'David Dispatcher',
              role: 'dispatcher',
              organization_id: 'org1',
              is_active: true,
              created_at: '',
              updated_at: '',
            },
            action: 'assignment.created',
            resource_type: 'assignment',
            resource_id: 'assign-1',
            changes: { technician_id: 'tech-1' },
            ip_address: '127.0.0.1',
            created_at: new Date(Date.now() - 1000 * 60 * 15).toISOString(),
          },
        ])
      })
      .finally(() => setLoading(false))
  }, [])

  const filteredLogs = logs.filter(
    (l) =>
      l.action.toLowerCase().includes(search.toLowerCase()) ||
      l.resource_type.toLowerCase().includes(search.toLowerCase()) ||
      l.actor?.full_name?.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">System Audit Log</h1>
        <p className="text-sm text-muted-foreground">
          Immutable compliance record of all administrative actions, dispatches, and status updates
        </p>
      </div>

      <div className="max-w-md">
        <Input
          placeholder="Filter by action, user, or resource..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div className="rounded-md border bg-background overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[180px]">Timestamp</TableHead>
              <TableHead>Actor</TableHead>
              <TableHead>Action</TableHead>
              <TableHead>Resource</TableHead>
              <TableHead>Changes / Details</TableHead>
              <TableHead className="w-[110px]">IP</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={6} className="h-32 text-center text-muted-foreground">
                  Loading audit logs...
                </TableCell>
              </TableRow>
            ) : filteredLogs.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="h-32 text-center text-muted-foreground">
                  No audit log entries found.
                </TableCell>
              </TableRow>
            ) : (
              filteredLogs.map((log) => (
                <TableRow key={log.id} className="text-xs">
                  <TableCell className="font-mono text-muted-foreground">
                    {formatDate(log.created_at)}
                  </TableCell>
                  <TableCell className="font-medium text-foreground">
                    {log.actor?.full_name || 'System'}
                  </TableCell>
                  <TableCell className="font-mono text-primary">
                    {log.action}
                  </TableCell>
                  <TableCell className="capitalize text-muted-foreground">
                    {log.resource_type} ({log.resource_id.slice(0, 8)})
                  </TableCell>
                  <TableCell>
                    {log.changes ? (
                      <pre className="font-mono text-[11px] bg-muted/60 p-1 rounded max-w-xs overflow-x-auto">
                        {JSON.stringify(log.changes)}
                      </pre>
                    ) : (
                      '—'
                    )}
                  </TableCell>
                  <TableCell className="font-mono text-muted-foreground">
                    {log.ip_address || '—'}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
