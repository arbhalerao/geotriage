import { useState, type ReactNode } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { useRegistered } from "../api/queries";
import { CheckItem, Collapsible, Panel, Rows } from "./Panel";
import { ToneText } from "./StatusBadge";
import type { Tone } from "../status";
import type { AdmissionResponse, Registered } from "../api/types";
import { formatDateTime } from "../time";

type Kind = "model" | "provider";

function Rejection({ image, problems, onDismiss }: { image: string; problems: string[]; onDismiss: () => void }) {
  return (
    <div role="alert" className="mt-4 rounded-lg border border-red-200 bg-red-50/60 text-sm">
      <div className="flex items-start gap-3 px-4 pt-3">
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-red-800">Couldn't add this image</p>
          <p className="font-mono text-xs text-gray-600 break-all">{image}</p>
        </div>
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss"
          className="shrink-0 w-6 h-6 flex items-center justify-center rounded text-gray-500 hover:text-gray-800 hover:bg-white/70 transition-colors"
        >
          ×
        </button>
      </div>
      <ul className="mx-4 mt-3 mb-4 space-y-2">
        {[...new Set(problems)].map((p) => (
          <li key={p} className="rounded border border-red-200 bg-white px-3 py-2 text-red-800 break-words">
            {p}
          </li>
        ))}
      </ul>
    </div>
  );
}

function AddForm({ kind, onAdded, onClose }: { kind: Kind; onAdded: () => void; onClose: () => void }) {
  const [image, setImage] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [problems, setProblems] = useState<string[] | null>(null);
  const register = useMutation({
    mutationFn: (ref: string) => api.post<AdmissionResponse>(`/${kind}s`, { image: ref }),
    onSuccess: (data) => {
      if (!data.admitted) return setProblems(data.problems);
      onAdded();
    },
  });

  return (
    <div
      className="bg-white border border-gray-200 rounded-lg p-5 mb-6"
      onKeyDown={(e) => {
        if (e.key === "Escape") onClose();
      }}
    >
      <h2 className="text-sm font-semibold mb-3">Add a {kind}</h2>

      <form
        className="flex flex-wrap gap-2 items-start"
        onSubmit={(e) => {
          e.preventDefault();
          setProblems(null);
          setSubmitted(image.trim());
          register.mutate(image.trim());
        }}
      >
        <input
          id={`${kind}-image`}
          value={image}
          // going back to the input means the error has been read; typing covers the case where focus never left it
          onFocus={() => setProblems(null)}
          onChange={(e) => {
            setImage(e.target.value);
            setProblems(null);
          }}
          placeholder="Enter the Docker image name and tag"
          aria-label={`${kind} image`}
          required
          autoFocus
          disabled={register.isPending}
          className="flex-1 min-w-56 bg-gray-100 border border-gray-300 rounded px-3 py-2 text-sm font-mono focus:outline-none focus:border-brand-500 disabled:text-gray-500"
        />

        <button
          type="submit"
          disabled={register.isPending || !image.trim()}
          className="text-sm px-4 py-2 bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white rounded transition-colors"
        >
          Add
        </button>
      </form>

      <div role="status" aria-live="polite">
        {register.isPending && <Progress>Checking the image…</Progress>}
      </div>

      {register.isError && (
        <p className="mt-3 text-xs text-red-700">
          The request failed: {(register.error as Error).message}
        </p>
      )}

      {problems && <Rejection image={submitted} problems={problems} onDismiss={() => setProblems(null)} />}
    </div>
  );
}

function Progress({ children }: { children: ReactNode }) {
  return (
    <p className="mt-3 flex items-center gap-2 text-sm text-gray-600">
      <span className="w-4 h-4 rounded-full border-2 border-gray-300 border-t-brand-600 animate-spin" aria-hidden />
      {children}
    </p>
  );
}

const STATUS: Record<string, { label: string; tone: Tone }> = {
  ready: { label: "Ready", tone: "good" },
  testing: { label: "Testing", tone: "progress" },
  failed: { label: "Failed", tone: "bad" },
};

export type CardDetails = {
  declared: [string, ReactNode][];
  sections?: ReactNode;
};

const CHECK_LABELS: Record<string, string> = {
  describe: "Built on the geotriage SDK",
  declarations: "Declarations are valid",
  "smoke run": "Scores a test scene",
  "smoke screen": "Screens a test scene",
  collections: "Collections not already taken",
};

function CheckList({ checks }: { checks: { name: string; passed: boolean; detail: string }[] }) {
  return (
    <ul className="space-y-1">
      {checks.map((c) => (
        <CheckItem key={c.name} state={c.detail.startsWith("queued") ? "queued" : c.passed ? "passed" : "failed"}>
          {CHECK_LABELS[c.name] ?? c.name}
        </CheckItem>
      ))}
    </ul>
  );
}

function RegisteredCard({ entry, details, onRemove }: { entry: Registered; details: CardDetails; onRemove: () => void }) {
  // a disabled model is either still being smoke-tested or has failed it
  // those look the same in is_enabled alone, and telling a user "running" forever would be a lie
  const pending = !entry.is_enabled && entry.admission?.smoke_pending === true;
  const failed = !entry.is_enabled && !pending;
  const status = STATUS[entry.is_enabled ? "ready" : pending ? "testing" : "failed"];
  const problems = entry.admission?.problems ?? [];
  const checks = entry.admission?.checks ?? [];
  const description = typeof entry.descriptor.description === "string" ? entry.descriptor.description : "";

  return (
    <Panel
      title={entry.name}
      subtitle={entry.slug}
      actions={
        <button
          type="button"
          onClick={onRemove}
          className="text-sm px-2.5 py-1 rounded text-gray-500 hover:text-red-700 hover:bg-red-50 transition-colors"
        >
          Remove
        </button>
      }
    >
      <Collapsible title="Details" defaultOpen>
        {description && <p className="text-sm text-gray-600 mb-4 max-w-3xl">{description}</p>}
        <Rows
          rows={[
            ...details.declared,
            ["Image", entry.image],
            ["Added", formatDateTime(entry.registered_at)],
          ]}
        />
      </Collapsible>

      {/* a failure opens it, since its errors need reading */}
      <Collapsible title="Status" defaultOpen={failed} summary={<ToneText tone={status.tone}>{status.label}</ToneText>}>
        {checks.length > 0 ? <CheckList checks={checks} /> : <p className="text-sm text-gray-500">No checks recorded.</p>}
        {failed && problems.length > 0 && (
          <div className="mt-3 rounded border border-red-200 bg-red-50/60 px-3 py-2.5 text-sm text-red-800">
            {problems.map((p, i) => (
              <p key={i} className="whitespace-pre-wrap break-words font-mono text-xs">
                {p}
              </p>
            ))}
            <p className="mt-2 text-xs text-red-700/80">Fix the image, rebuild it, and add it again to replace this one.</p>
          </div>
        )}
      </Collapsible>

      {details.sections}
    </Panel>
  );
}

export default function RegistrySection({
  kind,
  adding,
  onClose,
  details,
}: {
  kind: Kind;
  adding: boolean;
  onClose: () => void;
  details: (entry: Registered) => CardDetails;
}) {
  const queryClient = useQueryClient();
  const { data: entries, isLoading } = useRegistered(kind);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["registered", kind] });
    // model compatibility depends on which providers exist, so both catalogues move
    queryClient.invalidateQueries({ queryKey: ["models"] });
    queryClient.invalidateQueries({ queryKey: ["collections"] });
  };

  const remove = useMutation({
    mutationFn: (id: string) => api.delete(`/${kind}s/${id}`),
    onSuccess: invalidate,
  });

  return (
    <section className="mb-10">
      {adding && (
        <AddForm
          kind={kind}
          onAdded={() => {
            invalidate();
            onClose();
          }}
          onClose={onClose}
        />
      )}

      {isLoading && <p className="text-gray-500 text-sm">Loading…</p>}
      {!isLoading && !entries?.length && (
        <div className="text-center py-20 text-gray-500">
          <p>No {kind}s yet.</p>
        </div>
      )}

      <div className="space-y-4">
        {entries?.map((e) => (
          <RegisteredCard key={e.id} entry={e} details={details(e)} onRemove={() => remove.mutate(e.id)} />
        ))}
      </div>
    </section>
  );
}
