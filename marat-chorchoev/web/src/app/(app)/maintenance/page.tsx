'use client'

import React, { useState, useEffect } from 'react'
import { Plus, Wrench, Calendar, Clock, AlertCircle } from 'lucide-react'
import { maintenanceApi, propertiesApi, categoriesApi } from '@/lib/api'
import type { MaintenancePlan, Property, Category, RequestPriority } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { formatDate } from '@/lib/utils'

export default function MaintenancePage() {
  const [plans, setPlans] = useState<MaintenancePlan[]>([])
  const [properties, setProperties] = useState<Property[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [loading, setLoading] = useState(true)
  const [dialogOpen, setDialogOpen] = useState(false)

  // Form
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [propertyId, setPropertyId] = useState('')
  const [categoryId, setCategoryId] = useState('')
  const [recurrenceRule, setRecurrenceRule] = useState('FREQ=MONTHLY')
  const [nextDueDate, setNextDueDate] = useState('')
  const [priority, setPriority] = useState<RequestPriority>('medium')
  const [submitting, setSubmitting] = useState(false)

  const loadData = async () => {
    try {
      const [pData, propsData, catsData] = await Promise.allSettled([
        maintenanceApi.list(),
        propertiesApi.list(),
        categoriesApi.list(),
      ])
      if (pData.status === 'fulfilled') setPlans(pData.value)
      if (propsData.status === 'fulfilled') setProperties(propsData.value)
      if (catsData.status === 'fulfilled') setCategories(catsData.value)
    } catch {
      // fallback sample
      setPlans([
        {
          id: 'plan-1',
          organization_id: 'org1',
          name: 'Quarterly HVAC Comprehensive Inspection',
          description: 'Filter replacements, refrigerant check, coil wash',
          status: 'active',
          recurrence_rule: 'FREQ=MONTHLY;INTERVAL=3',
          next_due_date: new Date(Date.now() + 1000 * 60 * 60 * 24 * 14).toISOString(),
          priority: 'medium',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
        {
          id: 'plan-2',
          organization_id: 'org1',
          name: 'Monthly Fire Alarm & Sprinkler Testing',
          description: 'Test all pull stations, check pressure gauges',
          status: 'active',
          recurrence_rule: 'FREQ=MONTHLY',
          next_due_date: new Date(Date.now() + 1000 * 60 * 60 * 24 * 5).toISOString(),
          priority: 'high',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    try {
      const created = await maintenanceApi.create({
        name,
        description,
        property_id: propertyId || undefined,
        category_id: categoryId || undefined,
        recurrence_rule: recurrenceRule,
        next_due_date: nextDueDate ? new Date(nextDueDate).toISOString() : new Date().toISOString(),
        priority,
      })
      setPlans((prev) => [...prev, created])
      setDialogOpen(false)
      setName('')
      setDescription('')
    } catch {
      alert('Failed to create maintenance plan')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Preventive Maintenance Plans</h1>
          <p className="text-sm text-muted-foreground">
            Automated recurring service schedules to avoid equipment breakdowns
          </p>
        </div>

        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button className="flex items-center gap-1.5">
              <Plus className="w-4 h-4" />
              New Maintenance Plan
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create Maintenance Plan</DialogTitle>
              <DialogDescription>
                Schedule recurring preventive service work
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={handleCreate} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="plan-name">Plan Title *</Label>
                <Input
                  id="plan-name"
                  placeholder="e.g. Monthly Elevator Safety Check"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="plan-desc">Description</Label>
                <textarea
                  id="plan-desc"
                  rows={2}
                  className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                  placeholder="Instructions for preventive routine..."
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Recurrence Frequency</Label>
                  <Select
                    value={recurrenceRule}
                    onValueChange={(val) => setRecurrenceRule(val)}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="FREQ=WEEKLY">Weekly</SelectItem>
                      <SelectItem value="FREQ=MONTHLY">Monthly</SelectItem>
                      <SelectItem value="FREQ=MONTHLY;INTERVAL=3">Quarterly</SelectItem>
                      <SelectItem value="FREQ=YEARLY">Annual</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="due">First Due Date</Label>
                  <Input
                    id="due"
                    type="date"
                    value={nextDueDate}
                    onChange={(e) => setNextDueDate(e.target.value)}
                    required
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Target Property</Label>
                  <Select value={propertyId} onValueChange={setPropertyId}>
                    <SelectTrigger>
                      <SelectValue placeholder="All / None" />
                    </SelectTrigger>
                    <SelectContent>
                      {properties.map((p) => (
                        <SelectItem key={p.id} value={p.id}>
                          {p.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label>Default Priority</Label>
                  <Select
                    value={priority}
                    onValueChange={(val: RequestPriority) => setPriority(val)}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="low">Low</SelectItem>
                      <SelectItem value="medium">Medium</SelectItem>
                      <SelectItem value="high">High</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <DialogFooter className="pt-4">
                <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" disabled={submitting}>
                  {submitting ? 'Creating...' : 'Create Plan'}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="h-40 rounded-lg bg-muted animate-pulse" />
          <div className="h-40 rounded-lg bg-muted animate-pulse" />
        </div>
      ) : plans.length === 0 ? (
        <div className="text-center py-12 border rounded-lg bg-card">
          <Wrench className="mx-auto h-12 w-12 text-muted-foreground/60 mb-2" />
          <h3 className="text-base font-semibold">No maintenance plans defined</h3>
          <p className="text-sm text-muted-foreground mt-1">
            Create recurring schedules to automatically trigger maintenance work orders.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {plans.map((plan) => (
            <Card key={plan.id} className="hover:border-primary/50 transition-colors">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between">
                  <CardTitle className="text-base font-semibold">{plan.name}</CardTitle>
                  <Badge variant="outline" className="capitalize text-xs">
                    {plan.status}
                  </Badge>
                </div>
                {plan.description && (
                  <CardDescription className="text-xs line-clamp-2">
                    {plan.description}
                  </CardDescription>
                )}
              </CardHeader>
              <CardContent className="space-y-2 text-xs text-muted-foreground">
                <div className="flex items-center gap-1.5">
                  <Clock className="w-3.5 h-3.5 text-primary" />
                  <span>Cadence: {plan.recurrence_rule.replace('FREQ=', '')}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <Calendar className="w-3.5 h-3.5 text-amber-500" />
                  <span>Next Due: {formatDate(plan.next_due_date)}</span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
