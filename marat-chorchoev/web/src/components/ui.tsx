"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { ApiError } from "@/lib/api";

// ---------------------------------------------------------------- Buttons

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger" | "ghost";
  loading?: boolean;
  small?: boolean;
};

export function Button({ variant = "primary", loading, small, disabled, children, className = "", ...rest }: ButtonProps) {
  return (
    <button
      type="button"
      {...rest}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={`btn btn-${variant}${small ? " btn-sm" : ""} ${className}`}
    >
      {loading ? <span className="spinner" aria-hidden="true" /> : null}
      {children}
    </button>
  );
}

// ---------------------------------------------------------------- Form fields

interface FieldShell {
  label: string;
  error?: string | null;
  hint?: string;
}

function Shell({ label, error, hint, id, children }: FieldShell & { id: string; children: ReactNode }) {
  return (
    <div className={`field${error ? " field-invalid" : ""}`}>
      <label htmlFor={id}>{label}</label>
      {children}
      {hint && !error ? (
        <p className="hint" id={`${id}-hint`}>
          {hint}
        </p>
      ) : null}
      {error ? (
        <p className="error-text" id={`${id}-error`} role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

const describedBy = (id: string, error?: string | null, hint?: string) =>
  error ? `${id}-error` : hint ? `${id}-hint` : undefined;

export function TextField({ label, error, hint, ...rest }: FieldShell & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId();
  return (
    <Shell label={label} error={error} hint={hint} id={id}>
      <input id={id} aria-invalid={!!error} aria-describedby={describedBy(id, error, hint)} {...rest} />
    </Shell>
  );
}

export function TextArea({ label, error, hint, ...rest }: FieldShell & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const id = useId();
  return (
    <Shell label={label} error={error} hint={hint} id={id}>
      <textarea id={id} aria-invalid={!!error} aria-describedby={describedBy(id, error, hint)} rows={4} {...rest} />
    </Shell>
  );
}

export function SelectField({
  label,
  error,
  hint,
  children,
  ...rest
}: FieldShell & SelectHTMLAttributes<HTMLSelectElement>) {
  const id = useId();
  return (
    <Shell label={label} error={error} hint={hint} id={id}>
      <select id={id} aria-invalid={!!error} aria-describedby={describedBy(id, error, hint)} {...rest}>
        {children}
      </select>
    </Shell>
  );
}

// ---------------------------------------------------------------- Layout bits

export function Card({ title, actions, children, className = "" }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`card ${className}`}>
      {title || actions ? (
        <header className="card-head">
          {title ? <h2>{title}</h2> : <span />}
          {actions ? <div className="card-actions">{actions}</div> : null}
        </header>
      ) : null}
      {children}
    </section>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        {subtitle ? <p className="muted">{subtitle}</p> : null}
      </div>
      {actions ? <div className="page-actions">{actions}</div> : null}
    </div>
  );
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="loading" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" /> {label}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <strong>{title}</strong>
      {children ? <p className="muted">{children}</p> : null}
    </div>
  );
}

export function ErrorNote({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  if (!error) return null;
  const err = error instanceof ApiError ? error : null;
  const forbidden = err?.status === 403;
  return (
    <div className="notice notice-error" role="alert">
      <div>
        <strong>{forbidden ? "You do not have access to this." : "Something went wrong."}</strong>
        <p>{err ? err.message : error instanceof Error ? error.message : "Unexpected error."}</p>
        {err?.requestId ? <p className="muted small">Reference: {err.requestId}</p> : null}
      </div>
      {onRetry && !forbidden ? (
        <Button variant="secondary" small onClick={onRetry}>
          Try again
        </Button>
      ) : null}
    </div>
  );
}

export function Notice({ kind = "info", children }: { kind?: "info" | "warn" | "success"; children: ReactNode }) {
  return (
    <div className={`notice notice-${kind}`} role={kind === "warn" ? "alert" : "status"}>
      <div>{children}</div>
    </div>
  );
}

export function Pagination({
  page,
  totalPages,
  total,
  onChange,
}: {
  page: number;
  totalPages: number;
  total: number;
  onChange: (page: number) => void;
}) {
  return (
    <nav className="pagination" aria-label="Pagination">
      <span className="muted">
        {total} result{total === 1 ? "" : "s"} · page {Math.min(page, Math.max(totalPages, 1))} of {Math.max(totalPages, 1)}
      </span>
      <div className="row">
        <Button variant="secondary" small disabled={page <= 1} onClick={() => onChange(page - 1)}>
          Previous
        </Button>
        <Button variant="secondary" small disabled={page >= totalPages} onClick={() => onChange(page + 1)}>
          Next
        </Button>
      </div>
    </nav>
  );
}

// ---------------------------------------------------------------- Modal + confirmation

export function Modal({
  title,
  open,
  onClose,
  children,
}: {
  title: string;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      // The `open` attribute must NOT be rendered by React, or showModal() is skipped and the
      // dialog appears as a plain in-flow box (no backdrop, no centering, no focus trap).
      if (typeof dialog.showModal === "function") dialog.showModal();
      else dialog.setAttribute("open", ""); // jsdom / very old browsers
    }
    if (!open && dialog.open) dialog.close?.();
  }, [open]);
  if (!open) return null;
  return (
    <dialog ref={ref} className="modal" aria-labelledby="modal-title" onClose={onClose} onCancel={onClose}>
      <h2 id="modal-title">{title}</h2>
      {children}
    </dialog>
  );
}

export function ConfirmButton({
  label,
  title,
  message,
  confirmLabel,
  onConfirm,
  loading,
  variant = "danger",
  small,
  needsReason,
  reasonLabel = "Reason",
}: {
  label: string;
  title: string;
  message: ReactNode;
  confirmLabel?: string;
  onConfirm: (reason: string) => void;
  loading?: boolean;
  variant?: "primary" | "secondary" | "danger";
  small?: boolean;
  needsReason?: boolean;
  reasonLabel?: string;
}) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const submit = () => {
    if (needsReason && reason.trim().length < 3) {
      setError(`${reasonLabel} must be at least 3 characters.`);
      return;
    }
    setOpen(false);
    onConfirm(reason.trim());
    setReason("");
    setError(null);
  };
  return (
    <>
      <Button variant={variant} small={small} loading={loading} onClick={() => setOpen(true)}>
        {label}
      </Button>
      <Modal title={title} open={open} onClose={() => setOpen(false)}>
        <div className="stack">
          <div>{message}</div>
          {needsReason ? (
            <TextArea label={reasonLabel} value={reason} onChange={(e) => setReason(e.target.value)} error={error} rows={3} />
          ) : null}
          <div className="row end">
            <Button variant="secondary" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button variant={variant === "danger" ? "danger" : "primary"} onClick={submit}>
              {confirmLabel ?? label}
            </Button>
          </div>
        </div>
      </Modal>
    </>
  );
}

// ---------------------------------------------------------------- Toasts

interface Toast {
  id: number;
  kind: "success" | "error";
  text: string;
}
const ToastContext = createContext<(kind: Toast["kind"], text: string) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((kind: Toast["kind"], text: string) => {
    const id = Date.now() + Math.random();
    setToasts((list) => [...list.slice(-3), { id, kind, text }]);
    setTimeout(() => setToasts((list) => list.filter((t) => t.id !== id)), 6000);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toasts" aria-live="polite" aria-atomic="false">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.kind}`} role={t.kind === "error" ? "alert" : "status"}>
            {t.text}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);
