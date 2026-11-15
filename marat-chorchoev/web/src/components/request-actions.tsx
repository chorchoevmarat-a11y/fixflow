"use client";

import { useState } from "react";
import { Button, Card, ConfirmButton, Notice, SelectField, TextArea } from "@/components/ui";
import { api, newCommandId } from "@/lib/api";
import { useAction, useApiQuery } from "@/lib/hooks";
import { requireText } from "@/lib/validation";
import type { Category, FileItem, InventoryItem, Page, RequestDetail } from "@/lib/types";

/** Lifecycle controls. Unavailable actions are absent; the backend still enforces every rule. */
export function RequestActions({ request }: { request: RequestDetail }) {
  const id = request.id;
  const allowed = new Set(request.allowed_actions);
  const post = (path: string, body: unknown = {}) => api.post(`/requests/${id}/${path}`, body);

  const triage = useAction((notes: string) => post("triage", { triage_notes: notes || null }), { success: "Report accepted for dispatch." });
  const cancel = useAction((reason: string) => post("cancel", { reason: reason || null }), { success: "Report canceled." });
  const close = useAction((reason: string) => post("close", { reason: reason || null }), { success: "Report closed." });
  const reopen = useAction((reason: string) => post("reopen", { reason }), { success: "Rework requested." });
  const accept = useAction(() => post("accept"), { success: "Job accepted." });
  const decline = useAction((reason: string) => post("decline", { reason }), { success: "Job declined." });
  const start = useAction(() => post("start"), { success: "Work started." });
  const unassign = useAction((reason: string) => post("unassign", { reason }), { success: "Technician unassigned." });

  const [triageNotes, setTriageNotes] = useState(request.triage_notes ?? "");

  if (request.allowed_actions.length === 0) {
    return (
      <Notice>
        No actions are available while this report is {request.status.replace("_", " ").toLowerCase()}.
      </Notice>
    );
  }

  return (
    <Card title="Actions">
      <div className="stack">
        {request.start_blocked_reason ? <Notice kind="warn">Work cannot start yet: {request.start_blocked_reason}</Notice> : null}
        {allowed.has("triage") ? (
          <div className="stack">
            <TextArea label="Dispatch notes (optional)" value={triageNotes} onChange={(e) => setTriageNotes(e.target.value)} rows={2} />
            <div>
              <Button loading={triage.isPending} onClick={() => triage.mutate(triageNotes)}>
                Accept for dispatch
              </Button>
            </div>
          </div>
        ) : null}
        <div className="row">
          {allowed.has("accept") ? (
            <Button loading={accept.isPending} onClick={() => accept.mutate(undefined)}>
              Accept job
            </Button>
          ) : null}
          {allowed.has("start") ? (
            <Button loading={start.isPending} onClick={() => start.mutate(undefined)}>
              Start work
            </Button>
          ) : null}
          {request.status === "ACCEPTED" && !allowed.has("start") && request.assigned_to_me ? (
            <Button disabled title={request.start_blocked_reason ?? ""}>
              Start work (waiting for approval)
            </Button>
          ) : null}
          {allowed.has("decline") ? (
            <ConfirmButton
              label="Decline job"
              title="Decline this job?"
              message="The request returns to the dispatch queue and the appointment is released."
              needsReason
              onConfirm={(r) => decline.mutate(r)}
              loading={decline.isPending}
            />
          ) : null}
          {allowed.has("unassign") ? (
            <ConfirmButton
              label="Unassign technician"
              title="Unassign the technician?"
              message="The request returns to the dispatch queue. The previous assignment stays in the history."
              needsReason
              variant="secondary"
              onConfirm={(r) => unassign.mutate(r)}
              loading={unassign.isPending}
            />
          ) : null}
          {allowed.has("close") ? (
            <ConfirmButton
              label={request.allowed_actions.includes("reopen") ? "Accept work and close" : "Close report"}
              title="Close this report?"
              message="Closing is final."
              confirmLabel="Close report"
              variant="primary"
              needsReason={!allowed.has("reopen")}
              onConfirm={(r) => close.mutate(r)}
              loading={close.isPending}
            />
          ) : null}
          {allowed.has("reopen") ? (
            <ConfirmButton
              label="Request rework"
              title="Request rework?"
              message="Tell the dispatcher what is still wrong."
              needsReason
              variant="secondary"
              onConfirm={(r) => reopen.mutate(r)}
              loading={reopen.isPending}
            />
          ) : null}
          {allowed.has("cancel") ? (
            <ConfirmButton
              label="Cancel report"
              title="Cancel this report?"
              message="Canceled reports cannot be reopened."
              needsReason={request.allowed_actions.includes("triage") || request.allowed_actions.includes("assign") || request.allowed_actions.includes("reschedule")}
              onConfirm={(r) => cancel.mutate(r)}
              loading={cancel.isPending}
            />
          ) : null}
        </div>
        <TechnicianWork request={request} />
      </div>
    </Card>
  );
}

function TechnicianWork({ request }: { request: RequestDetail }) {
  const allowed = new Set(request.allowed_actions);
  const id = request.id;
  const [blockReason, setBlockReason] = useState("");
  const [resolution, setResolution] = useState("");
  const [note, setNote] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [item, setItem] = useState("");
  const [qty, setQty] = useState("1");
  const inventory = useApiQuery<Page<InventoryItem>>(allowed.has("consume_material") ? "/inventory" : null, { page_size: 100 });
  const files = useApiQuery<FileItem[]>(allowed.has("complete") ? `/requests/${id}/files` : null);

  const block = useAction(() => api.post(`/requests/${id}/block`, { reason: blockReason.trim() }), { success: "Marked as blocked." });
  const unblock = useAction(() => api.post(`/requests/${id}/unblock`, { resolution_note: resolution.trim() }), { success: "Work resumed." });
  const upload = useAction(
    async (file: File) => {
      const form = new FormData();
      form.set("file", file);
      form.set("kind", "COMPLETION");
      form.set("client_command_id", newCommandId("done"));
      return api.upload(`/requests/${id}/files`, form);
    },
    { success: "Photo added." },
  );
  const complete = useAction(
    () =>
      api.post(`/requests/${id}/complete`, {
        completion_note: note.trim(),
        materials: [],
      }),
    { success: "Job completed." },
  );
  const consume = useAction(
    (line: { item_id: string; quantity: number }) =>
      api.post(`/requests/${id}/materials`, { ...line, client_command_id: newCommandId("mat") }),
    { success: "Materials recorded." },
  );

  const completionPhotos = files.data?.filter((f) => f.kind === "COMPLETION").length ?? 0;

  if (!allowed.has("block") && !allowed.has("unblock") && !allowed.has("complete")) return null;

  return (
    <div className="stack">
      {allowed.has("unblock") ? (
        <div className="stack">
          <Notice kind="warn">Blocked: {request.blocker_reason}</Notice>
          <TextArea label="Resolution note" value={resolution} onChange={(e) => setResolution(e.target.value)} error={errors.resolution} rows={2} />
          <div>
            <Button
              loading={unblock.isPending}
              onClick={() => {
                const e = requireText(resolution, "Resolution note");
                setErrors(e ? { resolution: e } : {});
                if (!e) unblock.mutate(undefined);
              }}
            >
              Resume work
            </Button>
          </div>
        </div>
      ) : null}
      {allowed.has("block") ? (
        <div className="stack">
          <TextArea label="Blocker reason" value={blockReason} onChange={(e) => setBlockReason(e.target.value)} error={errors.block} rows={2} hint="Required to report a blocker" />
          <div>
            <Button
              variant="secondary"
              loading={block.isPending}
              onClick={() => {
                const e = requireText(blockReason, "Blocker reason");
                setErrors(e ? { block: e } : {});
                if (!e) block.mutate(undefined);
              }}
            >
              Report blocker
            </Button>
          </div>
        </div>
      ) : null}
      {allowed.has("consume_material") ? (
        <div className="stack">
          <h3>Materials</h3>
          <div className="grid cols-3">
            <SelectField label="Item" value={item} onChange={(e) => setItem(e.target.value)}>
              <option value="">Choose…</option>
              {inventory.data?.items.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.code} — {i.name} ({i.stock_quantity} {i.unit} in stock)
                </option>
              ))}
            </SelectField>
            <div className="field">
              <label htmlFor="mat-qty">Quantity</label>
              <input id="mat-qty" type="number" min={1} value={qty} onChange={(e) => setQty(e.target.value)} />
            </div>
            <div style={{ alignSelf: "end" }}>
              <Button
                variant="secondary"
                loading={consume.isPending}
                disabled={!item || !Number.isInteger(Number(qty)) || Number(qty) < 1}
                onClick={() => consume.mutate({ item_id: item, quantity: Number(qty) })}
              >
                Use now
              </Button>
            </div>
          </div>
          <p className="hint">Stock is deducted immediately and cannot go below zero.</p>
        </div>
      ) : null}
      {allowed.has("complete") ? (
        <div className="stack">
          <h3>Complete the job</h3>
          <div className="field">
            <label htmlFor="done-photo">Completion photo (required)</label>
            <input
              id="done-photo"
              type="file"
              accept="image/jpeg,image/png,image/webp"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) upload.mutate(f);
                e.target.value = "";
              }}
            />
            <p className="hint">{completionPhotos} completion photo(s) uploaded</p>
          </div>
          <TextArea label="Completion note" value={note} onChange={(e) => setNote(e.target.value)} error={errors.note} hint="At least 20 characters" rows={3} />
          <div>
            <Button
              loading={complete.isPending}
              onClick={() => {
                const trimmed = note.trim();
                const e = trimmed.length < 20 ? "Completion note must be at least 20 characters." : completionPhotos < 1 ? "Add at least one completion photo." : null;
                setErrors(e ? { note: e } : {});
                if (!e) complete.mutate(undefined);
              }}
            >
              Complete job
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

/** Category/priority change with a mandatory reason (REQ-03). */
export function ReclassifyCard({ request }: { request: RequestDetail }) {
  const categories = useApiQuery<Category[]>("/categories", { enabled_only: true });
  const [category, setCategory] = useState(request.category.id);
  const [priority, setPriority] = useState(request.priority);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [duplicate, setDuplicate] = useState("");
  const change = useAction(
    () =>
      api.post(`/requests/${request.id}/reclassify`, {
        category_id: category !== request.category.id ? category : null,
        priority: priority !== request.priority ? priority : null,
        reason: reason.trim(),
      }),
    { success: "Classification updated.", onSuccess: () => setReason("") },
  );
  const link = useAction((target: string | null) => api.post(`/requests/${request.id}/duplicate`, { duplicate_of_id: target }), {
    success: "Duplicate link updated.",
  });
  const changed = category !== request.category.id || priority !== request.priority;
  return (
    <Card title="Classification & duplicates">
      <div className="stack">
        <div className="grid cols-2">
          <SelectField
            label="Category"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            disabled={!["SUBMITTED", "TRIAGED", "REOPENED"].includes(request.status)}
          >
            {categories.data?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
            {!categories.data?.some((c) => c.id === request.category.id) ? <option value={request.category.id}>{request.category.name}</option> : null}
          </SelectField>
          <SelectField label="Priority" value={priority} onChange={(e) => setPriority(e.target.value as RequestDetail["priority"])}>
            <option value="LOW">Low</option>
            <option value="NORMAL">Normal</option>
            <option value="HIGH">High</option>
          </SelectField>
        </div>
        {changed ? (
          <>
            <TextArea label="Reason for the change" value={reason} onChange={(e) => setReason(e.target.value)} error={error} rows={2} />
            <div>
              <Button
                loading={change.isPending}
                onClick={() => {
                  const e = requireText(reason, "Reason");
                  setError(e);
                  if (!e) change.mutate(undefined);
                }}
              >
                Save change
              </Button>
            </div>
          </>
        ) : null}
        <hr style={{ border: 0, borderTop: "1px solid var(--border)", width: "100%" }} />
        {request.duplicate_of ? (
          <div className="row between">
            <span>
              Duplicate of <a href={`/requests/${request.duplicate_of.id}`}>{request.duplicate_of.reference}</a>
            </span>
            <Button variant="secondary" small loading={link.isPending} onClick={() => link.mutate(null)}>
              Remove link
            </Button>
          </div>
        ) : (
          <div className="row">
            <div className="field" style={{ flex: 1 }}>
              <label htmlFor="dup">Related report ID (UUID from its page URL)</label>
              <input id="dup" value={duplicate} onChange={(e) => setDuplicate(e.target.value.trim())} placeholder="Paste a report id" />
            </div>
            <Button variant="secondary" disabled={duplicate.length < 32} loading={link.isPending} onClick={() => link.mutate(duplicate)} style={{ alignSelf: "end" }}>
              Mark duplicate
            </Button>
          </div>
        )}
      </div>
    </Card>
  );
}
