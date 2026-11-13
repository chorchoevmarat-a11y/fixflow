export interface RequestFormValues {
  title: string;
  description: string;
  category_id: string;
  property_id: string;
  priority: string;
  preferred_start_at?: string;
  preferred_end_at?: string;
}

export type Errors = Record<string, string>;

/** Client-side mirror of the server rules; the server remains authoritative (REQ-02). */
export function validateRequestForm(v: RequestFormValues): Errors {
  const errors: Errors = {};
  const title = v.title.trim();
  const description = v.description.trim();
  if (!title) errors.title = "Title is required.";
  else if (title.length < 5) errors.title = "Title must be at least 5 characters.";
  else if (title.length > 120) errors.title = "Title must be at most 120 characters.";
  if (!description) errors.description = "Description is required.";
  else if (description.length < 20) errors.description = "Describe the problem in at least 20 characters.";
  else if (description.length > 3000) errors.description = "Description must be at most 3,000 characters.";
  if (!v.category_id) errors.category_id = "Choose a category.";
  if (!v.property_id) errors.property_id = "Choose a property.";
  const start = v.preferred_start_at ? new Date(v.preferred_start_at).getTime() : null;
  const end = v.preferred_end_at ? new Date(v.preferred_end_at).getTime() : null;
  if (start !== null && Number.isNaN(start)) errors.preferred_start_at = "Enter a valid date and time.";
  if (end !== null && Number.isNaN(end)) errors.preferred_end_at = "Enter a valid date and time.";
  if (!errors.preferred_start_at && !errors.preferred_end_at) {
    const latest = end ?? start;
    if (start !== null && end !== null && end <= start) errors.preferred_end_at = "Must end after the start.";
    else if (latest !== null && latest <= Date.now()) {
      errors[end !== null ? "preferred_end_at" : "preferred_start_at"] = "Choose a date and time in the future.";
    }
  }
  return errors;
}

export function requireText(value: string, label: string, min = 3): string | null {
  const text = value.trim();
  if (!text) return `${label} is required.`;
  if (text.length < min) return `${label} must be at least ${min} characters.`;
  return null;
}
