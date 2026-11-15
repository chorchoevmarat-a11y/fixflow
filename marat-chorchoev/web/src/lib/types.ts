export type Status =
  | "SUBMITTED"
  | "TRIAGED"
  | "SCHEDULED"
  | "ACCEPTED"
  | "IN_PROGRESS"
  | "BLOCKED"
  | "COMPLETED"
  | "REOPENED"
  | "CLOSED"
  | "CANCELED";
export type Priority = "LOW" | "NORMAL" | "HIGH";
export type SlaStateName = "ON_TRACK" | "AT_RISK" | "OVERDUE";

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface Sla {
  state: SlaStateName;
  budget_seconds: number;
  consumed_seconds: number;
  remaining_seconds: number;
  due_at: string | null;
  paused: boolean;
  stopped_at: string | null;
  escalated_at: string | null;
}

export interface AssignmentView {
  id: string;
  technician_id: string;
  technician_name: string | null;
  start_at: string;
  end_at: string;
  status: string;
  is_active: boolean;
}

export interface RequestRow {
  id: string;
  reference: string;
  title: string;
  status: Status;
  priority: Priority;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  requester_name: string;
  property: { id: string; name: string; address: string };
  category: { id: string; name: string };
  asset_id: string | null;
  assignment: AssignmentView | null;
  sla: Sla;
  is_preventive: boolean;
}

export interface EstimateLine {
  id: string;
  description: string;
  quantity: number;
  unit_price_minor: number;
  line_total_minor: number;
}

export type EstimateStatus = "DRAFT" | "AWAITING_APPROVAL" | "APPROVED" | "REJECTED" | "SUPERSEDED";

export interface Estimate {
  id: string;
  request_id: string;
  version: number;
  previous_version_id: string | null;
  status: EstimateStatus;
  labor_minutes: number;
  labor_rate_minor: number;
  labor_total_minor: number;
  materials_total_minor: number;
  total_minor: number;
  currency: string;
  notes: string | null;
  lines: EstimateLine[];
  created_by: string | null;
  created_at: string;
  submitted_by: string | null;
  submitted_at: string | null;
  decided_by: string | null;
  decided_at: string | null;
  decision_reason: string | null;
  request_reference?: string;
  request_title?: string;
}

export interface RequestDetail extends Omit<RequestRow, "property" | "category"> {
  description: string;
  /** Set by the server when an identical open request already existed and was returned instead. */
  deduplicated?: boolean;
  organization: { id: string; name: string; timezone: string };
  requester: { id: string; full_name: string; email?: string };
  property: { id: string; name: string; address: string; contact_instructions: string | null };
  category: { id: string; name: string; default_duration_minutes: number; is_enabled: boolean };
  asset: {
    id: string;
    code: string;
    name: string;
    asset_type: string;
    status: string;
    serial_number: string | null;
  } | null;
  preferred_start_at: string | null;
  preferred_end_at: string | null;
  duplicate_of: { id: string; reference: string; title: string } | null;
  estimate: { id: string; version: number; status: EstimateStatus; total_minor: number; currency: string } | null;
  start_blocked_reason: string | null;
  completion_note: string | null;
  blocker_reason: string | null;
  maintenance_plan_id: string | null;
  occurrence_date: string | null;
  feedback: { rating: number; comment: string | null; created_at: string } | null;
  closed_at: string | null;
  canceled_at: string | null;
  assigned_to_me: boolean;
  allowed_actions: string[];
  triage_notes?: string | null;
  has_draft_estimate?: boolean;
}

export interface Category {
  id: string;
  name: string;
  description: string;
  default_duration_minutes: number;
  is_enabled: boolean;
  required_skills: { id: string; name: string }[];
}

export interface PropertyItem {
  id: string;
  name: string;
  address: string;
  contact_instructions: string | null;
  is_shared: boolean;
  is_active: boolean;
  requesters?: { membership_id: string; full_name: string }[];
  asset_count?: number;
}

export interface AssetItem {
  id: string;
  property_id: string;
  property_name: string | null;
  code: string;
  name: string;
  asset_type: string;
  serial_number: string | null;
  installed_on: string | null;
  status: "ACTIVE" | "OUT_OF_SERVICE" | "RETIRED";
  notes: string | null;
}

export interface Candidate {
  technician_id: string;
  full_name: string;
  skills: string[];
  missing_skills: string[];
  eligible: boolean;
  reasons: { code: string; message: string }[];
  workload: { day_minutes: number; week_minutes: number; week_jobs: number };
}

export interface SlotOption {
  technician_id: string;
  technician_name: string;
  start_at: string;
  end_at: string;
  week_minutes: number;
  matches_preference: boolean;
}

export interface NoteItem {
  id: string;
  author_name: string;
  author_role: string;
  body: string;
  visibility: "PUBLIC" | "INTERNAL";
  created_at: string;
  attachments: { id: string; original_name: string }[];
}

export interface FileItem {
  id: string;
  kind: "INTAKE" | "NOTE" | "COMPLETION";
  original_name: string;
  content_url: string;
  uploaded_by: string | null;
  created_at: string;
  width: number;
  height: number;
}

export interface MaterialUsage {
  id: string;
  item_name: string;
  item_code: string;
  unit: string;
  quantity: number;
  technician_name: string;
  unit_price_minor?: number;
  total_minor?: number;
  created_at: string;
}

export interface ActivityItem {
  id: string;
  action: string;
  summary: string;
  actor_name: string;
  created_at: string;
}

export interface InventoryItem {
  id: string;
  code: string;
  name: string;
  unit: string;
  stock_quantity: number;
  reorder_threshold?: number;
  unit_price_minor?: number;
  is_low_stock?: boolean;
  is_active: boolean;
}

export interface NotificationItem {
  id: string;
  type: string;
  title: string;
  body: string;
  request_id: string | null;
  created_at: string;
  read_at: string | null;
}

export interface StaffMember {
  membership_id: string;
  user_id: string;
  email: string;
  full_name: string;
  role: "REQUESTER" | "DISPATCHER" | "ADMIN" | "TECHNICIAN";
  is_active: boolean;
  technician_id: string | null;
}

export interface Technician {
  id: string;
  full_name: string;
  email: string;
  title: string | null;
  phone: string | null;
  is_active: boolean;
  skills: { id: string; name: string }[];
  availability: { weekday: number; starts_at: string; ends_at: string }[];
  time_off: { id: string; start_at: string; end_at: string; reason: string | null }[];
}
