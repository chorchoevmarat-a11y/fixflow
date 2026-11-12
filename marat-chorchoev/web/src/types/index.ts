// ─── Enums ────────────────────────────────────────────────────────────────────

export type UserRole = 'admin' | 'dispatcher' | 'technician' | 'tenant'

export type RequestStatus =
  | 'new'
  | 'triaged'
  | 'assigned'
  | 'in_progress'
  | 'on_hold'
  | 'resolved'
  | 'closed'
  | 'cancelled'

export type RequestPriority = 'low' | 'medium' | 'high' | 'urgent'

export type AssignmentStatus =
  | 'pending'
  | 'accepted'
  | 'declined'
  | 'in_progress'
  | 'completed'

export type EstimateStatus = 'draft' | 'sent' | 'approved' | 'rejected'

export type MaintenancePlanStatus = 'active' | 'paused' | 'completed'

export type InventoryTransactionType = 'in' | 'out' | 'adjustment'

// ─── Core Domain Types ────────────────────────────────────────────────────────

export interface Organization {
  id: string
  name: string
  slug: string
  logo_url?: string
  plan: 'starter' | 'professional' | 'enterprise'
  settings: OrganizationSettings
  created_at: string
  updated_at: string
}

export interface OrganizationSettings {
  sla_enabled: boolean
  default_sla_hours: number
  currency: string
  timezone: string
  notification_email?: string
}

export interface User {
  id: string
  email: string
  full_name: string
  phone?: string
  role: UserRole
  organization_id: string
  avatar_url?: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface Property {
  id: string
  organization_id: string
  name: string
  address: string
  type: 'residential' | 'commercial' | 'industrial'
  floors?: number
  units?: number
  created_at: string
  updated_at: string
}

export interface Category {
  id: string
  organization_id: string
  name: string
  description?: string
  default_priority: RequestPriority
  default_sla_hours?: number
  parent_id?: string
  children?: Category[]
}

export interface ServiceRequest {
  id: string
  organization_id: string
  request_number: string
  title: string
  description: string
  status: RequestStatus
  priority: RequestPriority
  category_id?: string
  category?: Category
  property_id?: string
  property?: Property
  unit_number?: string
  requester_id: string
  requester?: User
  dispatcher_id?: string
  dispatcher?: User
  tags: string[]
  attachments: Attachment[]
  sla_deadline?: string
  sla_breached: boolean
  created_at: string
  updated_at: string
  resolved_at?: string
  closed_at?: string
}

export interface Attachment {
  id: string
  filename: string
  content_type: string
  size: number
  url: string
  created_at: string
}

export interface Assignment {
  id: string
  request_id: string
  request?: ServiceRequest
  technician_id: string
  technician?: User
  status: AssignmentStatus
  scheduled_start?: string
  scheduled_end?: string
  actual_start?: string
  actual_end?: string
  notes?: string
  created_at: string
  updated_at: string
}

export interface Note {
  id: string
  request_id: string
  author_id: string
  author?: User
  content: string
  is_internal: boolean
  attachments: Attachment[]
  created_at: string
  updated_at: string
}

export interface ActivityLog {
  id: string
  request_id: string
  actor_id: string
  actor?: User
  action: string
  details?: Record<string, unknown>
  created_at: string
}

export interface Estimate {
  id: string
  request_id: string
  request?: ServiceRequest
  created_by_id: string
  created_by?: User
  status: EstimateStatus
  line_items: EstimateLineItem[]
  subtotal_tyiyn: number
  tax_tyiyn: number
  total_tyiyn: number
  notes?: string
  valid_until?: string
  created_at: string
  updated_at: string
}

export interface EstimateLineItem {
  id: string
  description: string
  quantity: number
  unit_price_tyiyn: number
  total_tyiyn: number
}

export interface InventoryItem {
  id: string
  organization_id: string
  sku: string
  name: string
  description?: string
  unit: string
  quantity_on_hand: number
  quantity_reserved: number
  reorder_point: number
  unit_cost_tyiyn: number
  location?: string
  created_at: string
  updated_at: string
}

export interface InventoryTransaction {
  id: string
  item_id: string
  item?: InventoryItem
  request_id?: string
  performed_by_id: string
  performed_by?: User
  type: InventoryTransactionType
  quantity: number
  note?: string
  created_at: string
}

export interface MaintenancePlan {
  id: string
  organization_id: string
  name: string
  description?: string
  property_id?: string
  property?: Property
  category_id?: string
  category?: Category
  status: MaintenancePlanStatus
  recurrence_rule: string
  next_due_date: string
  last_generated_at?: string
  priority: RequestPriority
  assignee_id?: string
  assignee?: User
  created_at: string
  updated_at: string
}

export interface Notification {
  id: string
  user_id: string
  title: string
  body: string
  type: string
  is_read: boolean
  request_id?: string
  created_at: string
}

export interface AuditLog {
  id: string
  organization_id: string
  actor_id: string
  actor?: User
  action: string
  resource_type: string
  resource_id: string
  changes?: Record<string, unknown>
  ip_address?: string
  created_at: string
}

// ─── API Response Types ───────────────────────────────────────────────────────

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  per_page: number
  pages: number
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
}

export interface ApiError {
  detail: string
  code?: string
}

// ─── Dashboard Stats ──────────────────────────────────────────────────────────

export interface DashboardStats {
  open_requests: number
  overdue_requests: number
  requests_today: number
  avg_resolution_hours: number
  requests_by_status: Record<RequestStatus, number>
  requests_by_priority: Record<RequestPriority, number>
  requests_trend: Array<{ date: string; count: number }>
  technician_utilization: Array<{
    technician: User
    assigned: number
    completed: number
  }>
}

// ─── Smart Dispatch ───────────────────────────────────────────────────────────

export interface SmartDispatchSuggestion {
  technician: User
  score: number
  reasons: string[]
  current_assignments: number
  skills_match: boolean
  proximity_score?: number
  availability: 'available' | 'busy' | 'offline'
}
