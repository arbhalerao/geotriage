import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { useRegistered } from "../api/queries";
import type { AdmissionResponse, Registered } from "../api/types";

type Kind = "model" | "provider";

function CheckRow({ name, passed, detail }: { name: string; passed: boolean; detail: string }) {
  const pending = detail.startsWith("queued");
  const mark = pending ? "…" : passed ? "✓" : "✕";
  const tone = pending
    ? "text-gray-500"
    : passed
      ? "text-green-600 dark:text-green-400"
      : "text-red-600 dark:text-red-400";
  return (
    <li className="flex gap-2 items-baseline">
      <span className={`font-mono ${tone}`}>{mark}</span>
      <span className="text-gray-700 dark:text-gray-300">{name}</span>
      {detail && <span className="text-gray-500 break-all">— {detail}</span>}
    </li>
  );
}

function AddForm({ kind, onDone }: { kind: Kind; onDone: () => void }) {
  const [image, setImage] = useState("");
  const [result, setResult] = useState<AdmissionResponse | null>(null);

  const register = useMutation({
    mutationFn: () => api.post<AdmissionResponse>(`/${kind}s`, { image: image.trim() }),
    onSuccess: (data) => {
      setResult(data);
      if (data.admitted) {
        setImage("");
        onDone();
      }
    },
  });

  return (
    <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-5 mb-6">
      <h2 className="text-sm font-semibold mb-1">Add a {kind}</h2>
      <p className="text-xs text-gray-500 mb-4">
        The image is pulled, asked to describe itself, and checked against the contract before it
        is accepted. Build it <code className="font-mono">FROM geotriage/sdk</code> — see the
        authoring guide.
      </p>

      <form
        className="flex flex-wrap gap-2 items-start"
        onSubmit={(e) => {
          e.preventDefault();
          setResult(null);
          register.mutate();
        }}
      >
        <input
          id={`${kind}-image`}
          value={image}
          onChange={(e) => setImage(e.target.value)}
          placeholder={kind === "model" ? "acme/ship-detector:1.2" : "acme/archive:1.0"}
          required
          className="flex-1 min-w-56 text-sm px-2 py-1.5 rounded border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-950 font-mono"
        />

        <button
          type="submit"
          disabled={register.isPending || !image.trim()}
          className="text-sm px-3 py-1.5 bg-blue-800 hover:bg-blue-700 disabled:opacity-50 text-blue-100 rounded transition-colors"
        >
          {register.isPending ? "Checking…" : "Check & add"}
        </button>
      </form>

      {register.isPending && (
        <p className="mt-3 text-xs text-gray-500">Running the image — this takes a few seconds.</p>
      )}

      {register.isError && (
        <p className="mt-3 text-xs text-red-500">
          The request failed: {(register.error as Error).message}
        </p>
      )}

      {result && (
        <div
          className={`mt-4 rounded border px-4 py-3 text-xs ${
            result.admitted
              ? "border-green-300 dark:border-green-900 bg-green-50 dark:bg-green-950/40"
              : "border-red-300 dark:border-red-900 bg-red-50 dark:bg-red-950/40"
          }`}
        >
          <p className="font-medium mb-2">
            {result.admitted ? "Added" : "Rejected — the image was not added"}
          </p>
          <ul className="space-y-1">
            {result.checks.map((c) => (
              <CheckRow key={c.name} {...c} />
            ))}
          </ul>
          {result.problems.length > 0 && (
            <ul className="mt-3 space-y-1 text-red-700 dark:text-red-300">
              {result.problems.map((p, i) => (
                <li key={i}>{p}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function RegisteredCard({ kind, entry, onRemove }: { kind: Kind; entry: Registered; onRemove: () => void }) {
  // a disabled model is either still being smoke-tested or has failed it
  // those look the same in is_enabled alone, and telling a user "running" forever would be a lie
  const pending = !entry.is_enabled && entry.admission?.smoke_pending === true;
  const failed = !entry.is_enabled && !pending;
  const problems = entry.admission?.problems ?? [];
  const d = entry.descriptor as Record<string, unknown>;
  const requires = (d.requires ?? {}) as { bands?: string[] };
  const scores = Object.keys((d.scores ?? {}) as Record<string, unknown>);
  const collections = Object.keys((d.collections ?? {}) as Record<string, unknown>);

  return (
    <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg px-5 py-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold">{entry.name}</span>
            {pending && (
              <span className="text-xs px-1.5 py-0.5 rounded bg-yellow-100 dark:bg-yellow-900/60 text-yellow-700 dark:text-yellow-300">
                smoke test running
              </span>
            )}
            {failed && (
              <span className="text-xs px-1.5 py-0.5 rounded bg-red-100 dark:bg-red-900/60 text-red-700 dark:text-red-300">
                failed its smoke test
              </span>
            )}
            {entry.is_enabled && (
              <span className="text-xs px-1.5 py-0.5 rounded bg-green-100 dark:bg-green-900/60 text-green-700 dark:text-green-300">
                ready
              </span>
            )}
          </div>
          <p className="text-xs text-gray-500 font-mono mt-1 break-all">{entry.image}</p>
          <p className="text-xs text-gray-600 dark:text-gray-400 mt-2">
            <span className="font-mono">{entry.slug}</span>
            {kind === "model" ? (
              <>
                {" · bands "}
                {(requires.bands ?? []).join(", ")}
                {" · scores "}
                {scores.join(", ")}
              </>
            ) : (
              <>
                {" · collections "}
                {collections.join(", ")}
              </>
            )}
          </p>
        </div>
        <button
          onClick={onRemove}
          className="shrink-0 text-xs px-3 py-1.5 bg-gray-100 dark:bg-gray-800 hover:bg-red-900 text-gray-600 dark:text-gray-400 hover:text-red-300 rounded transition-colors"
        >
          Remove
        </button>
      </div>

      {failed && problems.length > 0 && (
        <div className="mt-3 rounded border border-red-300 dark:border-red-900 bg-red-50 dark:bg-red-950/40 px-3 py-2 text-xs text-red-700 dark:text-red-300">
          <p className="font-medium mb-1">Why it was disabled</p>
          {problems.map((p, i) => (
            <p key={i} className="whitespace-pre-wrap break-words font-mono">
              {p}
            </p>
          ))}
          <p className="mt-2 text-red-600/80 dark:text-red-400/80">
            Fix the image, rebuild it, and add the same slug again to replace it.
          </p>
        </div>
      )}
    </div>
  );
}

export default function RegistrySection({ kind }: { kind: Kind }) {
  const queryClient = useQueryClient();
  const { data: entries, isLoading } = useRegistered(kind);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["registered", kind] });
    // the catalogue only lists what a workflow can select, so it moves too
    queryClient.invalidateQueries({ queryKey: [kind === "model" ? "models" : "collections"] });
  };

  const remove = useMutation({
    mutationFn: (id: string) => api.delete(`/${kind}s/${id}`),
    onSuccess: invalidate,
  });

  return (
    <section className="mb-10">
      <AddForm kind={kind} onDone={invalidate} />

      {isLoading && <p className="text-gray-500 text-sm">Loading…</p>}
      {!isLoading && !entries?.length && (
        <p className="text-gray-500 text-sm">
          No {kind}s yet. Add one above, or run <code className="font-mono">make builtins</code> in
          the geotriage-sdk repo and restart to get the defaults.
        </p>
      )}

      <div className="space-y-3">
        {entries?.map((e) => (
          <RegisteredCard key={e.id} kind={kind} entry={e} onRemove={() => remove.mutate(e.id)} />
        ))}
      </div>
    </section>
  );
}
