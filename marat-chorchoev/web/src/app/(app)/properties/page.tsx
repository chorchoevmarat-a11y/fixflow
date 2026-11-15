"use client";

import Link from "next/link";
import { useState } from "react";
import { AuthGuard } from "@/components/auth-guard";
import { Button, Card, Empty, ErrorNote, Modal, PageHeader, Pagination, SelectField, Spinner, TextField } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useAction, useApiQuery } from "@/lib/hooks";
import type { AssetItem, Page, PropertyItem, StaffMember } from "@/lib/types";

function PropertyForm({ existing, onDone }: { existing?: PropertyItem; onDone: () => void }) {
  const [name, setName] = useState(existing?.name ?? "");
  const [address, setAddress] = useState(existing?.address ?? "");
  const [instructions, setInstructions] = useState(existing?.contact_instructions ?? "");
  const [shared, setShared] = useState(existing?.is_shared ?? true);
  const [selected, setSelected] = useState<string[]>(existing?.requesters?.map((r) => r.membership_id) ?? []);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const requesters = useApiQuery<Page<StaffMember>>("/staff", { role: "REQUESTER", is_active: true, page_size: 100 });
  const save = useAction(
    () => {
      const body = {
        name: name.trim(),
        address: address.trim(),
        contact_instructions: instructions.trim() || null,
        is_shared: shared,
        requester_membership_ids: shared ? [] : selected,
      };
      return existing ? api.patch(`/properties/${existing.id}`, body) : api.post("/properties", body);
    },
    { success: existing ? "Property updated." : "Property created.", onSuccess: onDone, silentError: true },
  );
  const server = save.error instanceof ApiError ? save.error.fields : {};
  const toggle = (id: string) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        const found: Record<string, string> = {};
        if (name.trim().length < 2) found.name = "Name is required.";
        if (address.trim().length < 5) found.address = "Enter the full address.";
        if (!shared && selected.length === 0) found.access = "Pick at least one requester, or allow all requesters.";
        setErrors(found);
        if (!Object.keys(found).length && !save.isPending) save.mutate(undefined);
      }}
    >
      <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} error={errors.name ?? server.name} />
      <TextField label="Address" value={address} onChange={(e) => setAddress(e.target.value)} error={errors.address ?? server.address} />
      <TextField label="Contact instructions (optional)" value={instructions} onChange={(e) => setInstructions(e.target.value)} />
      <fieldset className="field">
        <legend>Who can file reports for this property?</legend>
        <label>
          <input type="radio" name="access" checked={shared} onChange={() => setShared(true)} /> All requesters in the organization
        </label>
        <label>
          <input type="radio" name="access" checked={!shared} onChange={() => setShared(false)} /> Only selected requesters
        </label>
        {!shared ? (
          <div className="stack" style={{ marginTop: "0.5rem" }}>
            {requesters.isLoading ? <Spinner /> : null}
            <ErrorNote error={requesters.error} />
            {requesters.data?.items.map((r) => (
              <label key={r.membership_id}>
                <input type="checkbox" checked={selected.includes(r.membership_id)} onChange={() => toggle(r.membership_id)} /> {r.full_name}{" "}
                <span className="muted small">{r.email}</span>
              </label>
            ))}
          </div>
        ) : null}
        {errors.access ? <p role="alert" className="error-text">{errors.access}</p> : null}
      </fieldset>
      {save.error && !Object.keys(server).length ? <ErrorNote error={save.error} /> : null}
      <div className="row end">
        <Button variant="secondary" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" loading={save.isPending}>
          {existing ? "Save changes" : "Create property"}
        </Button>
      </div>
    </form>
  );
}

function AssetForm({ properties, onDone }: { properties: PropertyItem[]; onDone: () => void }) {
  const [form, setForm] = useState({ property_id: properties[0]?.id ?? "", code: "", name: "", asset_type: "", serial_number: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const create = useAction(
    () => api.post("/assets", { ...form, code: form.code.trim(), name: form.name.trim(), asset_type: form.asset_type.trim(), serial_number: form.serial_number.trim() || null }),
    { success: "Asset created.", onSuccess: onDone, silentError: true },
  );
  const server = create.error instanceof ApiError ? create.error.fields : {};
  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));
  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        const found: Record<string, string> = {};
        if (!/^[A-Za-z0-9._/-]{2,60}$/.test(form.code.trim())) found.code = "Code: 2–60 letters, digits, . _ / -";
        if (form.name.trim().length < 2) found.name = "Name is required.";
        if (form.asset_type.trim().length < 2) found.asset_type = "Type is required.";
        setErrors(found);
        if (!Object.keys(found).length && !create.isPending) create.mutate(undefined);
      }}
    >
      <SelectField label="Property" value={form.property_id} onChange={(e) => set("property_id", e.target.value)}>
        {properties.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </SelectField>
      <TextField label="Asset code (unique)" value={form.code} onChange={(e) => set("code", e.target.value)} error={errors.code ?? server.code} />
      <TextField label="Name" value={form.name} onChange={(e) => set("name", e.target.value)} error={errors.name ?? server.name} />
      <TextField label="Type" value={form.asset_type} onChange={(e) => set("asset_type", e.target.value)} error={errors.asset_type ?? server.asset_type} />
      <TextField label="Serial number (optional)" value={form.serial_number} onChange={(e) => set("serial_number", e.target.value)} />
      {create.error && !Object.keys(server).length ? <ErrorNote error={create.error} /> : null}
      <div className="row end">
        <Button variant="secondary" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" loading={create.isPending}>
          Create asset
        </Button>
      </div>
    </form>
  );
}

function PropertiesView() {
  const [pageNo, setPageNo] = useState(1);
  const [assetPage, setAssetPage] = useState(1);
  const [q, setQ] = useState("");
  const [propertyFilter, setPropertyFilter] = useState("");
  const [modal, setModal] = useState<"property" | "asset" | null>(null);
  const [editing, setEditing] = useState<PropertyItem | null>(null);
  const properties = useApiQuery<Page<PropertyItem>>("/properties", { page: pageNo, page_size: 10, q, include_inactive: true });
  const allProps = useApiQuery<Page<PropertyItem>>("/properties", { page_size: 100 });
  const assets = useApiQuery<Page<AssetItem>>("/assets", { page: assetPage, page_size: 10, property_id: propertyFilter });
  return (
    <>
      <PageHeader
        title="Properties & assets"
        actions={
          <>
            <Button onClick={() => { setEditing(null); setModal("property"); }}>Add property</Button>
            <Button variant="secondary" disabled={!allProps.data?.items.length} onClick={() => setModal("asset")}>
              Add asset
            </Button>
          </>
        }
      />
      <div className="stack">
        <Card title="Properties">
          <TextField label="Search" type="search" value={q} onChange={(e) => { setQ(e.target.value); setPageNo(1); }} />
          {properties.isLoading ? <Spinner /> : null}
          <ErrorNote error={properties.error} />
          {properties.data?.items.length === 0 ? <Empty title="No properties" /> : null}
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Address</th>
                  <th>Access</th>
                  <th>Assets</th>
                  <th>
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {properties.data?.items.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <button className="btn btn-ghost btn-sm" onClick={() => { setPropertyFilter(p.id); setAssetPage(1); }}>
                        {p.name}
                      </button>
                      {!p.is_active ? <span className="badge">inactive</span> : null}
                    </td>
                    <td>
                      {p.address}
                      {p.contact_instructions ? <div className="muted small">{p.contact_instructions}</div> : null}
                    </td>
                    <td>{p.is_shared ? "All requesters" : `Restricted (${p.requesters?.length ?? 0})`}</td>
                    <td>{p.asset_count}</td>
                    <td>
                      <Button small variant="secondary" onClick={() => { setEditing(p); setModal("property"); }}>
                        Edit access
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {properties.data ? <Pagination page={properties.data.page} totalPages={properties.data.total_pages} total={properties.data.total} onChange={setPageNo} /> : null}
        </Card>
        <Card
          title="Assets"
          actions={
            propertyFilter ? (
              <Button small variant="secondary" onClick={() => setPropertyFilter("")}>
                Clear property filter
              </Button>
            ) : undefined
          }
        >
          {assets.isLoading ? <Spinner /> : null}
          <ErrorNote error={assets.error} />
          {assets.data?.items.length === 0 ? <Empty title="No assets" /> : null}
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Name</th>
                  <th>Property</th>
                  <th>Type</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {assets.data?.items.map((a) => (
                  <tr key={a.id}>
                    <td>
                      <Link href={`/assets/${a.id}`}>{a.code}</Link>
                    </td>
                    <td>{a.name}</td>
                    <td>{a.property_name}</td>
                    <td>{a.asset_type}</td>
                    <td>
                      <span className="badge">{a.status.replace("_", " ").toLowerCase()}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {assets.data ? <Pagination page={assets.data.page} totalPages={assets.data.total_pages} total={assets.data.total} onChange={setAssetPage} /> : null}
        </Card>
      </div>
      <Modal title={editing ? `Edit ${editing.name}` : "Add property"} open={modal === "property"} onClose={() => setModal(null)}>
        {modal === "property" ? <PropertyForm key={editing?.id ?? "new"} existing={editing ?? undefined} onDone={() => setModal(null)} /> : null}
      </Modal>
      <Modal title="Add asset" open={modal === "asset"} onClose={() => setModal(null)}>
        <AssetForm properties={allProps.data?.items ?? []} onDone={() => setModal(null)} />
      </Modal>
    </>
  );
}

export default function PropertiesPage() {
  return (
    <AuthGuard roles={["ADMIN", "DISPATCHER"]}>
      <PropertiesView />
    </AuthGuard>
  );
}
