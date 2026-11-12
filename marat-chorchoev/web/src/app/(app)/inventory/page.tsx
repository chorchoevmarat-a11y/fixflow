'use client'

import React, { useState, useEffect } from 'react'
import { Plus, Package, AlertTriangle, ArrowDownUp, Search } from 'lucide-react'
import { inventoryApi } from '@/lib/api'
import type { InventoryItem, InventoryTransactionType } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
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
import { formatCurrency } from '@/lib/utils'

export default function InventoryPage() {
  const [items, setItems] = useState<InventoryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [addDialogOpen, setAddDialogOpen] = useState(false)
  const [transactDialogOpen, setTransactDialogOpen] = useState(false)
  const [selectedItem, setSelectedItem] = useState<InventoryItem | null>(null)

  // New item form
  const [sku, setSku] = useState('')
  const [name, setName] = useState('')
  const [unit, setUnit] = useState('pcs')
  const [quantity, setQuantity] = useState(0)
  const [reorderPoint, setReorderPoint] = useState(5)
  const [costKgs, setCostKgs] = useState(0)

  // Transaction form
  const [transType, setTransType] = useState<InventoryTransactionType>('in')
  const [transQuantity, setTransQuantity] = useState(1)
  const [transNote, setTransNote] = useState('')

  const loadInventory = async () => {
    try {
      const data = await inventoryApi.list()
      if (data && Array.isArray(data.items)) {
        setItems(data.items)
      } else if (Array.isArray(data)) {
        setItems(data)
      }
    } catch {
      // sample data
      setItems([
        {
          id: 'inv-1',
          organization_id: 'org1',
          sku: 'HVAC-FLT-2020',
          name: 'Air Filter 20x20x1 Merv 8',
          unit: 'pcs',
          quantity_on_hand: 24,
          quantity_reserved: 4,
          reorder_point: 10,
          unit_cost_tyiyn: 35000,
          location: 'Warehouse Shelf A-2',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
        {
          id: 'inv-2',
          organization_id: 'org1',
          sku: 'PLB-VALV-050',
          name: '1/2" Brass Ball Valve',
          unit: 'pcs',
          quantity_on_hand: 3,
          quantity_reserved: 1,
          reorder_point: 5,
          unit_cost_tyiyn: 48000,
          location: 'Warehouse Shelf B-1',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadInventory()
  }, [])

  const handleAddItem = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const created = await inventoryApi.create({
        sku,
        name,
        unit,
        quantity_on_hand: quantity,
        reorder_point: reorderPoint,
        unit_cost_tyiyn: Math.round(costKgs * 100),
      })
      setItems((prev) => [...prev, created])
      setAddDialogOpen(false)
      setSku('')
      setName('')
      setCostKgs(0)
    } catch {
      alert('Failed to add item')
    }
  }

  const handleTransact = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedItem) return

    try {
      await inventoryApi.transact(selectedItem.id, {
        type: transType,
        quantity: transQuantity,
        note: transNote,
      })
      setTransactDialogOpen(false)
      loadInventory()
    } catch {
      alert('Failed to record stock movement')
    }
  }

  const filteredItems = items.filter(
    (i) =>
      i.name.toLowerCase().includes(search.toLowerCase()) ||
      i.sku.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Spare Parts & Inventory</h1>
          <p className="text-sm text-muted-foreground">
            Track materials, stock consumption, and reorder levels
          </p>
        </div>

        <Dialog open={addDialogOpen} onOpenChange={setAddDialogOpen}>
          <DialogTrigger asChild>
            <Button className="flex items-center gap-1.5">
              <Plus className="w-4 h-4" />
              Add Inventory Item
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Add Inventory Item</DialogTitle>
              <DialogDescription>
                Register a new replacement component or material
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={handleAddItem} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="sku">SKU Code *</Label>
                  <Input
                    id="sku"
                    placeholder="e.g. ELEC-BREAKER-16A"
                    value={sku}
                    onChange={(e) => setSku(e.target.value)}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="unit">Unit of Measure</Label>
                  <Input
                    id="unit"
                    placeholder="pcs, meters, kg"
                    value={unit}
                    onChange={(e) => setUnit(e.target.value)}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="name">Item Name *</Label>
                <Input
                  id="name"
                  placeholder="e.g. 16A Circuit Breaker Schneider"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                />
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div className="space-y-2">
                  <Label htmlFor="qty">Initial Qty</Label>
                  <Input
                    id="qty"
                    type="number"
                    value={quantity}
                    onChange={(e) => setQuantity(parseInt(e.target.value) || 0)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="reorder">Reorder Point</Label>
                  <Input
                    id="reorder"
                    type="number"
                    value={reorderPoint}
                    onChange={(e) => setReorderPoint(parseInt(e.target.value) || 0)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="cost">Unit Cost (KGS)</Label>
                  <Input
                    id="cost"
                    type="number"
                    step="0.01"
                    value={costKgs}
                    onChange={(e) => setCostKgs(parseFloat(e.target.value) || 0)}
                  />
                </div>
              </div>

              <DialogFooter className="pt-4">
                <Button type="button" variant="outline" onClick={() => setAddDialogOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit">Save Item</Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {/* Search */}
      <div className="max-w-md">
        <Input
          placeholder="Search by SKU or item name..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {/* Items Table */}
      <div className="rounded-md border bg-background overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[140px]">SKU</TableHead>
              <TableHead>Item Name</TableHead>
              <TableHead className="w-[120px]">Location</TableHead>
              <TableHead className="w-[100px] text-right">In Stock</TableHead>
              <TableHead className="w-[120px] text-right">Unit Cost</TableHead>
              <TableHead className="w-[120px]">Stock Status</TableHead>
              <TableHead className="w-[120px] text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={7} className="h-32 text-center text-muted-foreground">
                  Loading inventory...
                </TableCell>
              </TableRow>
            ) : filteredItems.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="h-32 text-center text-muted-foreground">
                  No inventory items found.
                </TableCell>
              </TableRow>
            ) : (
              filteredItems.map((item) => {
                const isLow = item.quantity_on_hand <= item.reorder_point
                return (
                  <TableRow key={item.id}>
                    <TableCell className="font-mono text-xs font-semibold">
                      {item.sku}
                    </TableCell>
                    <TableCell className="font-medium">{item.name}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {item.location || '—'}
                    </TableCell>
                    <TableCell className="text-right font-semibold">
                      {item.quantity_on_hand} {item.unit}
                    </TableCell>
                    <TableCell className="text-right text-xs">
                      {formatCurrency(item.unit_cost_tyiyn)}
                    </TableCell>
                    <TableCell>
                      {isLow ? (
                        <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full bg-rose-100 text-rose-800 dark:bg-rose-950/40 dark:text-rose-400">
                          <AlertTriangle className="w-3 h-3" />
                          Low Stock
                        </span>
                      ) : (
                        <span className="inline-flex items-center text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-400">
                          Healthy
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7 text-xs"
                        onClick={() => {
                          setSelectedItem(item)
                          setTransactDialogOpen(true)
                        }}
                      >
                        Adjust Stock
                      </Button>
                    </TableCell>
                  </TableRow>
                )
              })
            )}
          </TableBody>
        </Table>
      </div>

      {/* Adjust Stock Dialog */}
      <Dialog open={transactDialogOpen} onOpenChange={setTransactDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Adjust Stock: {selectedItem?.name}</DialogTitle>
            <DialogDescription>
              Record incoming shipment, technician consumption, or inventory recount
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleTransact} className="space-y-4">
            <div className="space-y-2">
              <Label>Transaction Type</Label>
              <Select
                value={transType}
                onValueChange={(val: InventoryTransactionType) => setTransType(val)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="in">Restock (+ Inbound)</SelectItem>
                  <SelectItem value="out">Usage / Consumption (- Outbound)</SelectItem>
                  <SelectItem value="adjustment">Count Adjustment</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="trans-qty">Quantity ({selectedItem?.unit})</Label>
              <Input
                id="trans-qty"
                type="number"
                min="1"
                value={transQuantity}
                onChange={(e) => setTransQuantity(parseInt(e.target.value) || 1)}
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="trans-note">Note / Reference</Label>
              <Input
                id="trans-note"
                placeholder="e.g. Used for REQ-1001 or PO #4910"
                value={transNote}
                onChange={(e) => setTransNote(e.target.value)}
              />
            </div>

            <DialogFooter className="pt-4">
              <Button type="button" variant="outline" onClick={() => setTransactDialogOpen(false)}>
                Cancel
              </Button>
              <Button type="submit">Confirm Adjustment</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
