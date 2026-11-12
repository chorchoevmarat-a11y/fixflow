import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios'
import {
  type Organization,
  type User,
  type ServiceRequest,
  type Assignment,
  type Note,
  type Estimate,
  type InventoryItem,
  type InventoryTransaction,
  type MaintenancePlan,
  type Category,
  type Property,
  type Notification,
  type AuditLog,
  type DashboardStats,
  type SmartDispatchSuggestion,
  type PaginatedResponse,
  type TokenResponse,
} from '@/types'
import { getToken, clearAuth } from '@/lib/auth'

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export const apiClient = axios.create({
  baseURL: `${BASE_URL}/api/v1`,
  headers: { 'Content-Type': 'application/json' },
})

// ─── Request interceptor: attach token + org id ───────────────────────────────
apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = getToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  const orgId =
    typeof window !== 'undefined'
      ? localStorage.getItem('fixflow_org_id')
      : null
  if (orgId) {
    config.headers['X-Organization-ID'] = orgId
  }
  return config
})

// ─── Response interceptor: handle auth errors ─────────────────────────────────
apiClient.interceptors.response.use(
  (res) => res,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      clearAuth()
      if (typeof window !== 'undefined') {
        window.location.href = '/login'
      }
    }
    if (error.response?.status === 403) {
      if (typeof window !== 'undefined') {
        window.location.href = '/forbidden'
      }
    }
    return Promise.reject(error)
  },
)

// ─── Auth ─────────────────────────────────────────────────────────────────────

export const authApi = {
  login: (email: string, password: string) =>
    apiClient.post<TokenResponse>('/auth/login', { email, password }).then((r) => r.data),

  me: () => apiClient.get<User>('/auth/me').then((r) => r.data),

  myOrganizations: () =>
    apiClient.get<Organization[]>('/auth/organizations').then((r) => r.data),

  logout: () => apiClient.post('/auth/logout').then((r) => r.data),
}

// ─── Requests ─────────────────────────────────────────────────────────────────

export interface RequestFilters {
  status?: string
  priority?: string
  category_id?: string
  property_id?: string
  assignee_id?: string
  search?: string
  page?: number
  per_page?: number
}

export const requestsApi = {
  list: (filters?: RequestFilters) =>
    apiClient
      .get<PaginatedResponse<ServiceRequest>>('/requests', { params: filters })
      .then((r) => r.data),

  get: (id: string) =>
    apiClient.get<ServiceRequest>(`/requests/${id}`).then((r) => r.data),

  create: (data: Partial<ServiceRequest>) =>
    apiClient.post<ServiceRequest>('/requests', data).then((r) => r.data),

  update: (id: string, data: Partial<ServiceRequest>) =>
    apiClient.patch<ServiceRequest>(`/requests/${id}`, data).then((r) => r.data),

  triage: (id: string, data: { priority: string; category_id?: string; notes?: string }) =>
    apiClient.post<ServiceRequest>(`/requests/${id}/triage`, data).then((r) => r.data),

  close: (id: string, resolution: string) =>
    apiClient
      .post<ServiceRequest>(`/requests/${id}/close`, { resolution })
      .then((r) => r.data),

  cancel: (id: string, reason: string) =>
    apiClient
      .post<ServiceRequest>(`/requests/${id}/cancel`, { reason })
      .then((r) => r.data),

  addNote: (id: string, data: { content: string; is_internal: boolean }) =>
    apiClient.post<Note>(`/requests/${id}/notes`, data).then((r) => r.data),

  getNotes: (id: string) =>
    apiClient.get<Note[]>(`/requests/${id}/notes`).then((r) => r.data),

  getActivity: (id: string) =>
    apiClient.get(`/requests/${id}/activity`).then((r) => r.data),

  uploadAttachment: (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return apiClient
      .post(`/requests/${id}/attachments`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((r) => r.data)
  },

  smartDispatch: (id: string) =>
    apiClient
      .get<SmartDispatchSuggestion[]>(`/requests/${id}/smart-dispatch`)
      .then((r) => r.data),
}

// ─── Assignments ──────────────────────────────────────────────────────────────

export const assignmentsApi = {
  create: (requestId: string, data: Partial<Assignment>) =>
    apiClient
      .post<Assignment>(`/requests/${requestId}/assignments`, data)
      .then((r) => r.data),

  list: (requestId: string) =>
    apiClient
      .get<Assignment[]>(`/requests/${requestId}/assignments`)
      .then((r) => r.data),

  update: (requestId: string, assignmentId: string, data: Partial<Assignment>) =>
    apiClient
      .patch<Assignment>(`/requests/${requestId}/assignments/${assignmentId}`, data)
      .then((r) => r.data),

  myAssignments: () =>
    apiClient.get<Assignment[]>('/assignments/me').then((r) => r.data),
}

// ─── Estimates ────────────────────────────────────────────────────────────────

export const estimatesApi = {
  get: (requestId: string) =>
    apiClient.get<Estimate>(`/requests/${requestId}/estimate`).then((r) => r.data),

  create: (requestId: string, data: Partial<Estimate>) =>
    apiClient
      .post<Estimate>(`/requests/${requestId}/estimate`, data)
      .then((r) => r.data),

  update: (requestId: string, data: Partial<Estimate>) =>
    apiClient
      .put<Estimate>(`/requests/${requestId}/estimate`, data)
      .then((r) => r.data),

  approve: (requestId: string) =>
    apiClient
      .post<Estimate>(`/requests/${requestId}/estimate/approve`)
      .then((r) => r.data),

  reject: (requestId: string, reason: string) =>
    apiClient
      .post<Estimate>(`/requests/${requestId}/estimate/reject`, { reason })
      .then((r) => r.data),
}

// ─── Inventory ────────────────────────────────────────────────────────────────

export const inventoryApi = {
  list: (params?: { search?: string; low_stock?: boolean }) =>
    apiClient
      .get<PaginatedResponse<InventoryItem>>('/inventory', { params })
      .then((r) => r.data),

  get: (id: string) =>
    apiClient.get<InventoryItem>(`/inventory/${id}`).then((r) => r.data),

  create: (data: Partial<InventoryItem>) =>
    apiClient.post<InventoryItem>('/inventory', data).then((r) => r.data),

  update: (id: string, data: Partial<InventoryItem>) =>
    apiClient.patch<InventoryItem>(`/inventory/${id}`, data).then((r) => r.data),

  transact: (id: string, data: Partial<InventoryTransaction>) =>
    apiClient
      .post<InventoryTransaction>(`/inventory/${id}/transactions`, data)
      .then((r) => r.data),

  transactions: (id: string) =>
    apiClient
      .get<InventoryTransaction[]>(`/inventory/${id}/transactions`)
      .then((r) => r.data),
}

// ─── Maintenance Plans ────────────────────────────────────────────────────────

export const maintenanceApi = {
  list: () =>
    apiClient.get<MaintenancePlan[]>('/maintenance-plans').then((r) => r.data),

  get: (id: string) =>
    apiClient.get<MaintenancePlan>(`/maintenance-plans/${id}`).then((r) => r.data),

  create: (data: Partial<MaintenancePlan>) =>
    apiClient
      .post<MaintenancePlan>('/maintenance-plans', data)
      .then((r) => r.data),

  update: (id: string, data: Partial<MaintenancePlan>) =>
    apiClient
      .patch<MaintenancePlan>(`/maintenance-plans/${id}`, data)
      .then((r) => r.data),

  delete: (id: string) =>
    apiClient.delete(`/maintenance-plans/${id}`).then((r) => r.data),
}

// ─── Properties ───────────────────────────────────────────────────────────────

export const propertiesApi = {
  list: () => apiClient.get<Property[]>('/properties').then((r) => r.data),

  get: (id: string) =>
    apiClient.get<Property>(`/properties/${id}`).then((r) => r.data),

  create: (data: Partial<Property>) =>
    apiClient.post<Property>('/properties', data).then((r) => r.data),

  update: (id: string, data: Partial<Property>) =>
    apiClient.patch<Property>(`/properties/${id}`, data).then((r) => r.data),

  delete: (id: string) =>
    apiClient.delete(`/properties/${id}`).then((r) => r.data),
}

// ─── Categories ───────────────────────────────────────────────────────────────

export const categoriesApi = {
  list: () => apiClient.get<Category[]>('/categories').then((r) => r.data),

  create: (data: Partial<Category>) =>
    apiClient.post<Category>('/categories', data).then((r) => r.data),

  update: (id: string, data: Partial<Category>) =>
    apiClient.patch<Category>(`/categories/${id}`, data).then((r) => r.data),

  delete: (id: string) =>
    apiClient.delete(`/categories/${id}`).then((r) => r.data),
}

// ─── Staff / Users ────────────────────────────────────────────────────────────

export const staffApi = {
  list: () => apiClient.get<User[]>('/staff').then((r) => r.data),

  get: (id: string) => apiClient.get<User>(`/staff/${id}`).then((r) => r.data),

  invite: (data: { email: string; full_name: string; role: string }) =>
    apiClient.post<User>('/staff/invite', data).then((r) => r.data),

  update: (id: string, data: Partial<User>) =>
    apiClient.patch<User>(`/staff/${id}`, data).then((r) => r.data),

  deactivate: (id: string) =>
    apiClient.post<User>(`/staff/${id}/deactivate`).then((r) => r.data),
}

// ─── Organization ─────────────────────────────────────────────────────────────

export const organizationApi = {
  get: () => apiClient.get<Organization>('/organization').then((r) => r.data),

  update: (data: Partial<Organization>) =>
    apiClient.patch<Organization>('/organization', data).then((r) => r.data),
}

// ─── Notifications ────────────────────────────────────────────────────────────

export const notificationsApi = {
  list: () =>
    apiClient.get<Notification[]>('/notifications').then((r) => r.data),

  markRead: (id: string) =>
    apiClient
      .post<Notification>(`/notifications/${id}/read`)
      .then((r) => r.data),

  markAllRead: () =>
    apiClient.post('/notifications/read-all').then((r) => r.data),
}

// ─── Audit Logs ───────────────────────────────────────────────────────────────

export const auditApi = {
  list: (params?: { resource_type?: string; actor_id?: string; page?: number }) =>
    apiClient
      .get<PaginatedResponse<AuditLog>>('/audit', { params })
      .then((r) => r.data),
}

// ─── Dashboard ────────────────────────────────────────────────────────────────

export const dashboardApi = {
  stats: () =>
    apiClient.get<DashboardStats>('/dashboard/stats').then((r) => r.data),
}

// ─── Reports ──────────────────────────────────────────────────────────────────

export const reportsApi = {
  summary: (params?: { from?: string; to?: string }) =>
    apiClient.get('/reports/summary', { params }).then((r) => r.data),

  technicianPerformance: (params?: { from?: string; to?: string }) =>
    apiClient
      .get('/reports/technician-performance', { params })
      .then((r) => r.data),

  slaCompliance: (params?: { from?: string; to?: string }) =>
    apiClient.get('/reports/sla-compliance', { params }).then((r) => r.data),
}
