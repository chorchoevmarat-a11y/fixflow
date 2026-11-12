'use client'

import React, { useState, useEffect } from 'react'
import { Plus, FolderTree, Trash2 } from 'lucide-react'
import { categoriesApi } from '@/lib/api'
import type { Category, RequestPriority } from '@/types'
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
import { PriorityBadge } from '@/components/priority-badge'

export default function CategoriesPage() {
  const [categories, setCategories] = useState<Category[]>([])
  const [loading, setLoading] = useState(true)
  const [dialogOpen, setDialogOpen] = useState(false)

  // Form
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [defaultPriority, setDefaultPriority] = useState<RequestPriority>('medium')
  const [defaultSlaHours, setDefaultSlaHours] = useState(24)
  const [submitting, setSubmitting] = useState(false)

  const loadCategories = async () => {
    try {
      const data = await categoriesApi.list()
      setCategories(data)
    } catch {
      // fallback sample
      setCategories([
        {
          id: 'cat-1',
          organization_id: 'org1',
          name: 'HVAC & Climate Control',
          description: 'Heating, AC, airflow, chillers, ventilation',
          default_priority: 'high',
          default_sla_hours: 12,
        },
        {
          id: 'cat-2',
          organization_id: 'org1',
          name: 'Plumbing & Drainage',
          description: 'Pipes, leaks, fixtures, water pressure, drainage',
          default_priority: 'high',
          default_sla_hours: 8,
        },
        {
          id: 'cat-3',
          organization_id: 'org1',
          name: 'Electrical & Power',
          description: 'Wiring, breakers, lighting, generators, outlets',
          default_priority: 'urgent',
          default_sla_hours: 4,
        },
        {
          id: 'cat-4',
          organization_id: 'org1',
          name: 'Janitorial & Cleaning',
          description: 'Spill cleanup, waste management, routine sanitation',
          default_priority: 'low',
          default_sla_hours: 24,
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadCategories()
  }, [])

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    try {
      const newCat = await categoriesApi.create({
        name,
        description,
        default_priority: defaultPriority,
        default_sla_hours: defaultSlaHours,
      })
      setCategories((prev) => [...prev, newCat])
      setDialogOpen(false)
      setName('')
      setDescription('')
    } catch {
      alert('Failed to add category')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (id: string) => {
    if (confirm('Delete this category?')) {
      try {
        await categoriesApi.delete(id)
        setCategories((prev) => prev.filter((c) => c.id !== id))
      } catch {
        alert('Failed to delete category')
      }
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Request Categories</h1>
          <p className="text-sm text-muted-foreground">
            Classify work requests, set default priorities, and custom SLA response windows
          </p>
        </div>

        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button className="flex items-center gap-1.5">
              <Plus className="w-4 h-4" />
              Add Category
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Add Request Category</DialogTitle>
              <DialogDescription>
                Define a new work classification
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={handleCreate} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="cat-name">Category Name *</Label>
                <Input
                  id="cat-name"
                  placeholder="e.g. Elevators & Lifts"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="cat-desc">Description</Label>
                <Input
                  id="cat-desc"
                  placeholder="Brief description of work types"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Default Priority</Label>
                  <Select
                    value={defaultPriority}
                    onValueChange={(val: RequestPriority) => setDefaultPriority(val)}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="low">Low</SelectItem>
                      <SelectItem value="medium">Medium</SelectItem>
                      <SelectItem value="high">High</SelectItem>
                      <SelectItem value="urgent">Urgent</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="sla">Target SLA (Hours)</Label>
                  <Input
                    id="sla"
                    type="number"
                    value={defaultSlaHours}
                    onChange={(e) => setDefaultSlaHours(parseInt(e.target.value) || 24)}
                    required
                  />
                </div>
              </div>

              <DialogFooter className="pt-4">
                <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" disabled={submitting}>
                  {submitting ? 'Creating...' : 'Create Category'}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {categories.map((c) => (
          <Card key={c.id}>
            <CardHeader className="flex flex-row items-start justify-between pb-2">
              <div>
                <CardTitle className="text-base font-semibold">{c.name}</CardTitle>
                {c.description && (
                  <CardDescription className="text-xs mt-1">{c.description}</CardDescription>
                )}
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-muted-foreground hover:text-destructive"
                onClick={() => handleDelete(c.id)}
              >
                <Trash2 className="w-4 h-4" />
              </Button>
            </CardHeader>
            <CardContent className="space-y-2 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Default Priority:</span>
                <PriorityBadge priority={c.default_priority} />
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">SLA Window:</span>
                <span className="font-semibold">{c.default_sla_hours || 24} hours</span>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}
