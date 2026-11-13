"use client";

import { useState } from "react";
import { AuthGuard } from "@/components/auth-guard";
import { Button, Card, Empty, ErrorNote, Modal, Notice, PageHeader, Pagination, Spinner, TextField } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { fmtMoney, parseMoney } from "@/lib/format";
import { useAction, useApiQuery } from "@/lib/hooks";
import { isStaff, useMembership } from "@/lib/session";
import type { InventoryItem, Page } from "@/lib/types";

function ItemForm({ onDone }: { onDone: () => void }) {
  const [f, setF] = useState({ code: "", name: "", unit: "pcs", stock: "0", threshold: "0", price: "0.00" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const create = useAction(
    () =>
      api.post("/inventory", {
        code: f.code.trim(),
        name: f.name.trim(),
        unit: f.unit.trim(),
        stock_quantity: Number(f.stock),
        reorder_threshold: Number(f.threshold),
        unit_price_minor: parseMoney(f.price),
      }),
    { success: "Item created.", onSuccess: onDone, silentError: true },
  );
  const server = create.error instanceof ApiError ? create.error.fields : {};
  const set = (k: string, v: string) => setF((s) => ({ ...s, [k]: v }));
  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        const found: Record<string, string> = {};
        if (!/^[A-Za-z0-9._/-]{2,60}$/.test(f.code.trim())) found.code = "Code: 2–60 letters, digits, . _ / -";
        if (f.name.trim().length < 2) found.name = "Name is required.";
        if (!f.unit.trim()) found.unit = "Unit is required.";
        if (!Number.isInteger(Number(f.stock)) || Number(f.stock) < 0) found.stock = "Whole number, zero or more.";
        if (!Number.isInteger(Number(f.threshold)) || Number(f.threshold) < 0) found.threshold = "Whole number, zero or more.";
        if (parseMoney(f.price) === null) found.price = "Enter an amount like 125.50.";
        setErrors(found);
        if (!Object.keys(found).length && !create.isPending) create.mutate(undefined);
      }}
    >
      <TextField label="Item code" value={f.code} onChange={(e) => set("code", e.target.value)} error={errors.code ?? server.code} />
      <TextField label="Name" value={f.name} onChange={(e) => set("name", e.target.value)} error={errors.name ?? server.name} />
      <div className="grid cols-2">
        <TextField label="Unit" value={f.unit} onChange={(e) => set("unit", e.target.value)} error={errors.unit} />
        <TextField label="Unit price (KGS)" value={f.price} onChange={(e) => set("price", e.target.value)} error={errors.price} />
        <TextField label="Opening stock" type="number" min={0} value={f.stock} onChange={(e) => set("stock", e.target.value)} error={errors.stock} />
        <TextField label="Reorder threshold" type="number" min={0} value={f.threshold} onChange={(e) => set("threshold", e.target.value)} error={errors.threshold} />
      </div>
      {create.error && !Object.keys(server).length ? <ErrorNote error={create.error} /> : null}
      <div className="row end">
        <Button variant="secondary" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" loading={create.isPending}>
          Create item
        </Button>
      </div>
    </form>
  );
}

function StockForm({ item, onDone }: { item: InventoryItem; onDone: () => void }) {
  const [qty, setQty] = useState("1");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const add = useAction(() => api.post(`/inventory/${item.id}/stock-additions`, { quantity: Number(qty), reason: reason.trim() }), {
    success: "Stock added.",
    onSuccess: onDone,
  });
  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        if (!Number.isInteger(Number(qty)) || Number(qty) < 1) return setError("Enter a whole number of 1 or more.");
        if (reason.trim().length < 3) return setError("Give a reason (3+ characters).");
        setError(null);
        if (!add.isPending) add.mutate(undefined);
      }}
    >
      <p>
        {item.code} — {item.name}: {item.stock_quantity} {item.unit} in stock
      </p>
      <TextField label="Quantity to add" type="number" min={1} value={qty} onChange={(e) => setQty(e.target.value)} />
      <TextField label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} error={error} />
      <div className="row end">
        <Button variant="secondary" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" loading={add.isPending}>
          Add stock
        </Button>
      </div>
    </form>
  );
}

function InventoryView() {
  const membership = useMembership();
  const admin = membership?.role === "ADMIN";
  const staff = isStaff(membership?.role);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [low, setLow] = useState(false);
  const [modal, setModal] = useState<"create" | InventoryItem | null>(null);
  const items = useApiQuery<Page<InventoryItem>>("/inventory", { page, page_size: 15, q, low_stock: low || undefined });
  const lowCount = useApiQuery<Page<InventoryItem>>(staff ? "/inventory" : null, { low_stock: true, page_size: 1 });
  return (
    <>
      <PageHeader title="Inventory" actions={admin ? <Button onClick={() => setModal("create")}>Add item</Button> : undefined} />
      {lowCount.data?.total ? <Notice kind="warn">{lowCount.data.total} item(s) are at or below their reorder threshold.</Notice> : null}
      <Card>
        <div className="row">
          <div style={{ flex: 1 }}>
            <TextField label="Search" type="search" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
          </div>
          {staff ? (
            <label className="check" style={{ marginTop: "1.4rem" }}>
              <input type="checkbox" checked={low} onChange={(e) => { setLow(e.target.checked); setPage(1); }} />
              Low stock only
            </label>
          ) : null}
        </div>
        {items.isLoading ? <Spinner /> : null}
        <ErrorNote error={items.error} onRetry={() => void items.refetch()} />
        {items.data?.items.length === 0 ? <Empty title="No items" /> : null}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Code</th>
                <th>Item</th>
                <th>In stock</th>
                {staff ? <th>Reorder at</th> : null}
                {staff ? <th>Unit price</th> : null}
                {admin ? <th /> : null}
              </tr>
            </thead>
            <tbody>
              {items.data?.items.map((i) => (
                <tr key={i.id}>
                  <td>{i.code}</td>
                  <td>{i.name}</td>
                  <td>
                    {i.stock_quantity} {i.unit}{" "}
                    {i.is_low_stock ? <span className="badge sla-AT_RISK">⚠ Low stock</span> : null}
                  </td>
                  {staff ? <td>{i.reorder_threshold}</td> : null}
                  {staff ? <td>{fmtMoney(i.unit_price_minor ?? 0)}</td> : null}
                  {admin ? (
                    <td>
                      <Button small variant="secondary" onClick={() => setModal(i)}>
                        Add stock
                      </Button>
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {items.data ? <Pagination page={items.data.page} totalPages={items.data.total_pages} total={items.data.total} onChange={setPage} /> : null}
      </Card>
      <Modal title="Add inventory item" open={modal === "create"} onClose={() => setModal(null)}>
        <ItemForm onDone={() => setModal(null)} />
      </Modal>
      <Modal title="Add stock" open={typeof modal === "object" && modal !== null} onClose={() => setModal(null)}>
        {typeof modal === "object" && modal ? <StockForm item={modal} onDone={() => setModal(null)} /> : null}
      </Modal>
    </>
  );
}

export default function InventoryPage() {
  return (
    <AuthGuard roles={["ADMIN", "DISPATCHER", "TECHNICIAN"]}>
      <InventoryView />
    </AuthGuard>
  );
}
