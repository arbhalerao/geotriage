import { createContext, useCallback, useContext, useEffect, useId, useMemo, useState, type ReactNode } from "react";
import Chevron from "./Chevron";

// a panel's rows report their open state here, so the panel can offer to open or close them all at once
type RowGroup = {
  isOpen: (id: string) => boolean;
  setOpen: (id: string, open: boolean) => void;
  register: (id: string, defaultOpen: boolean) => void;
  unregister: (id: string) => void;
};

const RowGroupContext = createContext<RowGroup | null>(null);

function useRowGroup() {
  const [open, setOpenState] = useState<Record<string, boolean>>({});

  // stable across renders, so a row's registration effect doesn't re-run, and reset it, every time something toggles
  const setOpen = useCallback((id: string, value: boolean) => setOpenState((prev) => ({ ...prev, [id]: value })), []);
  // a row seen for the first time takes its default; one already known keeps its state
  const register = useCallback((id: string, defaultOpen: boolean) => setOpenState((prev) => (id in prev ? prev : { ...prev, [id]: defaultOpen })), []);
  const unregister = useCallback(
    (id: string) =>
      setOpenState((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      }),
    [],
  );
  const setAll = useCallback((value: boolean) => setOpenState((prev) => Object.fromEntries(Object.keys(prev).map((id) => [id, value]))), []);

  const group = useMemo<RowGroup>(() => ({ isOpen: (id) => open[id] ?? false, setOpen, register, unregister }), [open, setOpen, register, unregister]);

  return { group, anyOpen: Object.values(open).some(Boolean), hasRows: Object.keys(open).length > 0, setAll };
}

export function Panel({
  title,
  subtitle,
  actions,
  sample = false,
  variant = "card",
  children,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  // "card" names a thing (a model, a provider); "section" is a part of a page and gets the small section title
  variant?: "card" | "section";
  sample?: boolean;
  children: ReactNode;
}) {
  const rows = useRowGroup();
  const muted = sample ? "grayscale opacity-60" : "";

  return (
    <RowGroupContext.Provider value={rows.group}>
      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
        <div className="px-5 py-4 flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h3 className={`${variant === "section" ? "text-sm font-medium text-gray-800" : "text-base font-semibold text-gray-900"} ${muted}`}>{title}</h3>
            {subtitle && <p className={`text-sm text-gray-500 ${muted}`}>{subtitle}</p>}
          </div>
          <div className="shrink-0 flex items-center gap-1">
            {rows.hasRows && (
              <button
                type="button"
                onClick={() => rows.setAll(!rows.anyOpen)}
                className="text-sm px-2.5 py-1 rounded text-gray-500 hover:text-gray-900 hover:bg-gray-100 transition-colors"
              >
                {rows.anyOpen ? "Collapse all" : "Expand all"}
              </button>
            )}
            {actions}
          </div>
        </div>
        <div className={muted}>{children}</div>
      </div>
    </RowGroupContext.Provider>
  );
}

export function PanelBody({ children }: { children: ReactNode }) {
  return <div className="px-5 pb-4">{children}</div>;
}

export function Collapsible({
  title,
  summary,
  defaultOpen = false,
  children,
}: {
  title: ReactNode;
  summary?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const id = useId();
  const group = useContext(RowGroupContext);
  const [localOpen, setLocalOpen] = useState(defaultOpen);

  const register = group?.register;
  const unregister = group?.unregister;
  useEffect(() => {
    if (!register || !unregister) return;
    register(id, defaultOpen);
    return () => unregister(id);
  }, [id, defaultOpen, register, unregister]);

  // inside a panel the group owns the state; on its own a row keeps it locally
  const open = group ? group.isOpen(id) : localOpen;
  const toggle = () => (group ? group.setOpen(id, !open) : setLocalOpen(!open));

  return (
    <div className="border-t border-gray-200">
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        className="w-full px-5 py-2.5 flex items-center gap-3 text-sm text-left hover:bg-gray-50 transition-colors"
      >
        <span className="min-w-0 flex-1 text-gray-800">{title}</span>
        {summary && <span className="shrink-0 text-gray-500">{summary}</span>}
        <Chevron open={open} className="text-gray-500" />
      </button>
      {open && <div className="px-5 pb-4 pt-1 overflow-x-auto">{children}</div>}
    </div>
  );
}

export function Rows({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[7.5rem_1fr] gap-x-4 gap-y-2 text-sm leading-6">
      {rows.map(([label, value]) => (
        <div key={label} className="contents">
          <dt className="text-gray-500">{label}</dt>
          <dd className="min-w-0 text-gray-900 break-words">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

const MARKS = {
  passed: { mark: "✓", cls: "bg-green-100 text-green-700" },
  failed: { mark: "✕", cls: "bg-red-100 text-red-700" },
  queued: { mark: "…", cls: "bg-gray-100 text-gray-500" },
};

export function CheckItem({ state, children, note }: { state: keyof typeof MARKS; children: ReactNode; note?: ReactNode }) {
  const icon = MARKS[state];
  return (
    <li className="flex items-start gap-2 text-sm leading-6">
      <span className={`mt-1 shrink-0 w-4 h-4 rounded-full flex items-center justify-center text-[10px] font-semibold ${icon.cls}`}>
        {icon.mark}
      </span>
      <span className="min-w-0">
        <span className={state === "queued" ? "text-gray-500" : "text-gray-900"}>{children}</span>
        {note && <span className="ml-2 text-gray-500">{note}</span>}
      </span>
    </li>
  );
}
