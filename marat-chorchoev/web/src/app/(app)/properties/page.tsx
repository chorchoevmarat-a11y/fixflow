'use client'

import React, { useState, useEffect } from 'react'
import { Plus, Building, MapPin, MoreHorizontal, Trash2 } from 'lucide-react'
import { propertiesApi } from '@/lib/api'
import type { Property } from '@/types'
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
import { Skeleton } from '@/components/ui/skeleton'

export default function PropertiesPage() {
  const [properties, setProperties] = useState<Property[]>([])
  const [loading, setLoading] = useState(true)
  const [dialogOpen, setDialogOpen] = useState(false)

  // Form state
  const [name, setName] = useState('')
  const [address, setAddress] = useState('')
  const [type, setType] = useState<'residential' | 'commercial' | 'industrial'>('commercial')
  const [units, setUnits] = useState<number>(10)
  const [submitting, setSubmitting] = useState(false)

  const loadProperties = async () => {
    try {
      const data = await propertiesApi.list()
      setProperties(data)
    } catch {
      // fallback sample
      setProperties([
        {
          id: 'prop-1',
          organization_id: 'org1',
          name: 'Central Plaza Headquarters',
          address: '142 Main St, Bishkek',
          type: 'commercial',
          units: 45,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
        {
          id: 'prop-2',
          organization_id: 'org1',
          name: 'Ala-Archa Business Park',
          address: '88 Manas Ave, Bishkek',
          type: 'commercial',
          units: 120,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadProperties()
  }, [])

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    try {
      const newProp = await propertiesApi.create({
        name,
        address,
        type,
        units,
      })
      setProperties((prev) => [...prev, newProp])
      setDialogOpen(false)
      setName('')
      setAddress('')
    } catch {
      alert('Failed to add property')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (id: string) => {
    if (confirm('Are you sure you want to delete this property?')) {
      try {
        await propertiesApi.delete(id)
        setProperties((prev) => prev.filter((p) => p.id !== id))
      } catch {
        alert('Failed to delete property')
      }
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Properties & Facilities</h1>
          <p className="text-sm text-muted-foreground">
            Manage buildings, commercial complexes, and real estate assets
          </p>
        </div>

        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button className="flex items-center gap-1.5">
              <Plus className="w-4 h-4" />
              Add Property
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Add New Property</DialogTitle>
              <DialogDescription>
                Register a building or facility for service maintenance
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={handleCreate} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="prop-name">Property Name *</Label>
                <Input
                  id="prop-name"
                  placeholder="e.g. West Tower Complex"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="prop-address">Address *</Label>
                <Input
                  id="prop-address"
                  placeholder="Street address, city"
                  value={address}
                  onChange={(e) => setAddress(e.target.value)}
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Property Type</Label>
                  <Select
                    value={type}
                    onValueChange={(val: 'residential' | 'commercial' | 'industrial') => setType(val)}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="commercial">Commercial</SelectItem>
                      <SelectItem value="residential">Residential</SelectItem>
                      <SelectItem value="industrial">Industrial</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="units">Units / Suites</Label>
                  <Input
                    id="units"
                    type="number"
                    value={units}
                    onChange={(e) => setUnits(parseInt(e.target.value) || 0)}
                  />
                </div>
              </div>

              <DialogFooter className="pt-4">
                <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" disabled={submitting}>
                  {submitting ? 'Adding...' : 'Add Property'}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Skeleton className="h-40 rounded-lg" />
          <Skeleton className="h-40 rounded-lg" />
          <Skeleton className="h-40 rounded-lg" />
        </div>
      ) : properties.length === 0 ? (
        <div className="text-center py-12 border rounded-lg bg-card">
          <Building className="mx-auto h-12 w-12 text-muted-foreground/60 mb-2" />
          <h3 className="text-base font-semibold">No properties registered</h3>
          <p className="text-sm text-muted-foreground mt-1">
            Add your managed properties to associate service requests and assets.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {properties.map((p) => (
            <Card key={p.id} className="hover:border-primary/50 transition-colors">
              <CardHeader className="flex flex-row items-start justify-between pb-2">
                <div>
                  <CardTitle className="text-base font-semibold">{p.name}</CardTitle>
                  <CardDescription className="capitalize text-xs">
                    {p.type} • {p.units || 0} units
                  </CardDescription>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 text-muted-foreground hover:text-destructive"
                  onClick={() => handleDelete(p.id)}
                >
                  <Trash2 className="w-4 h-4" />
                </Button>
              </CardHeader>
              <CardContent className="text-sm space-y-2">
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <MapPin className="w-3.5 h-3.5 shrink-0" />
                  <span className="truncate">{p.address}</span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
