export interface RequestFormValues {
  title: string;
  description: string;
  category_id: string;
  property_id: string;
  priority: string;
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
  return errors;
}

export function requireText(value: string, label: string, min = 3): string | null {
  const text = value.trim();
  if (!text) return `${label} is required.`;
  if (text.length < min) return `${label} must be at least ${min} characters.`;
  return null;
}
