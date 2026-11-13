"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, type FormEvent } from "react";
import { Button, Card, ErrorNote, Notice, SelectField, TextArea, TextField } from "@/components/ui";
import { api, ApiError, newCommandId } from "@/lib/api";
import { useAction, useApiQuery } from "@/lib/hooks";
import { validateRequestForm, type Errors } from "@/lib/validation";
import type { AssetItem, Category, Page, PropertyItem, RequestDetail } from "@/lib/types";

/** Request intake form: client validation mirrors the server, which stays authoritative. */
export function RequestForm() {
  const router = useRouter();
  const categories = useApiQuery<Category[]>("/categories", { enabled_only: true });
  const properties = useApiQuery<Page<PropertyItem>>("/properties", { page_size: 100 });
  const [values, setValues] = useState({ title: "", description: "", category_id: "", property_id: "", asset_id: "", priority: "NORMAL" });
  const [prefStart, setPrefStart] = useState("");
  const [prefEnd, setPrefEnd] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [errors, setErrors] = useState<Errors>({});
  const [fileError, setFileError] = useState<string | null>(null);
  const key = useRef(newCommandId("req"));

  const assets = useApiQuery<Page<AssetItem>>(values.property_id ? "/assets" : null, {
    property_id: values.property_id,
    page_size: 100,
  });

  const create = useAction(
    async () => {
      const body = {
        title: values.title.trim(),
        description: values.description.trim(),
        category_id: values.category_id,
        property_id: values.property_id,
        asset_id: values.asset_id || null,
        priority: values.priority,
        preferred_start_at: prefStart ? new Date(prefStart).toISOString() : null,
        preferred_end_at: prefEnd ? new Date(prefEnd).toISOString() : null,
      };
      const created = await api.post<RequestDetail>("/requests", body, { "Idempotency-Key": key.current });
      for (const file of files) {
        const form = new FormData();
        form.set("file", file);
        form.set("kind", "INTAKE");
        form.set("client_command_id", newCommandId("img"));
        await api.upload(`/requests/${created.id}/files`, form);
      }
      return created;
    },
    {
      success: "Request submitted.",
      onSuccess: (created) => router.push(`/requests/${created.id}`),
      silentError: true,
    },
  );

  function onFiles(list: FileList | null) {
    const picked = Array.from(list ?? []);
    if (picked.length > 3) {
      setFileError("You can attach at most 3 images.");
      return;
    }
    const bad = picked.find((f) => !["image/jpeg", "image/png", "image/webp"].includes(f.type) || f.size > 10 * 1024 * 1024);
    if (bad) {
      setFileError(`${bad.name}: only JPEG, PNG, or WebP images up to 10 MiB are accepted.`);
      return;
    }
    setFileError(null);
    setFiles(picked);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (create.isPending) return;
    const found = validateRequestForm(values);
    setErrors(found);
    if (Object.keys(found).length || fileError) return;
    create.mutate(undefined);
  }

  const serverErrors = create.error instanceof ApiError ? create.error.fields : {};
  const err = (name: string) => errors[name] ?? serverErrors[name];
  const set = (name: string, value: string) => setValues((v) => ({ ...v, [name]: value, ...(name === "property_id" ? { asset_id: "" } : {}) }));

  return (
    <form onSubmit={submit} noValidate className="stack" aria-label="New service request">
      <Card title="What needs fixing?">
        <div className="stack">
          <TextField label="Title" value={values.title} onChange={(e) => set("title", e.target.value)} error={err("title")} hint="5–120 characters" maxLength={140} />
          <TextArea
            label="Description"
            value={values.description}
            onChange={(e) => set("description", e.target.value)}
            error={err("description")}
            hint={`${values.description.trim().length}/3000 — at least 20 characters`}
            rows={6}
          />
          <div className="grid cols-2">
            <SelectField label="Category" value={values.category_id} onChange={(e) => set("category_id", e.target.value)} error={err("category_id")}>
              <option value="">Choose…</option>
              {categories.data?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </SelectField>
            <SelectField label="Priority" value={values.priority} onChange={(e) => set("priority", e.target.value)} hint="High = 8 business hours, Normal = 24, Low = 48">
              <option value="LOW">Low</option>
              <option value="NORMAL">Normal</option>
              <option value="HIGH">High</option>
            </SelectField>
            <SelectField label="Property" value={values.property_id} onChange={(e) => set("property_id", e.target.value)} error={err("property_id")}>
              <option value="">Choose…</option>
              {properties.data?.items.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} — {p.address}
                </option>
              ))}
            </SelectField>
            <SelectField label="Equipment (optional)" value={values.asset_id} onChange={(e) => set("asset_id", e.target.value)} error={err("asset_id")} disabled={!values.property_id}>
              <option value="">No specific equipment</option>
              {assets.data?.items.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.code} — {a.name}
                </option>
              ))}
            </SelectField>
          </div>
        </div>
      </Card>
      <Card title="Preferred visit and photos (optional)">
        <div className="grid cols-2">
          <TextField label="Preferred from" type="datetime-local" value={prefStart} onChange={(e) => setPrefStart(e.target.value)} />
          <TextField label="Preferred until" type="datetime-local" value={prefEnd} onChange={(e) => setPrefEnd(e.target.value)} />
        </div>
        <div className="field" style={{ marginTop: "0.75rem" }}>
          <label htmlFor="intake-images">Photos (up to 3)</label>
          <input id="intake-images" type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={(e) => onFiles(e.target.files)} />
          {fileError ? (
            <p className="error-text" role="alert">
              {fileError}
            </p>
          ) : (
            <p className="hint">{files.length ? `${files.length} selected` : "JPEG, PNG, or WebP, up to 10 MiB each"}</p>
          )}
        </div>
      </Card>
      {create.error && !(create.error instanceof ApiError && create.error.status === 422 && Object.keys(serverErrors).length) ? (
        <ErrorNote error={create.error} />
      ) : null}
      {create.isError && files.length ? <Notice kind="warn">If the request was created but a photo failed, open it from your list and add photos there.</Notice> : null}
      <div className="row end">
        <Button type="submit" loading={create.isPending}>
          Submit request
        </Button>
      </div>
    </form>
  );
}
