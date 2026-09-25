import { useEffect, useState } from "react";
import { useBuilderRun, useModels, useStartBuilderRun } from "../api/queries";
import Chevron from "./Chevron";
import type { BuilderDraft, BuilderMessage, StorageEstimateResult } from "../api/types";

type Stopped = { request: string | null; steps: string[]; at: number; reason: string };

type Drafted = { request: string; warnings: string[] };

// said in different ways on purpose: a question, a plain request, a named satellite, relative dates;
// each is shown only while the detector it needs is registered, since models come and go without a release
const EXAMPLES: { text: string; needs: string }[] = [
  { text: "Watch for flooding around Dhaka every day until the end of October", needs: "ndwi-water-detector" },
  { text: "How hot did Phoenix, Arizona get in July 2025?", needs: "lst-detector" },
  { text: "Track the water in Lake Urmia during 2023", needs: "ndwi-water-detector" },
  { text: "Map water around Patna in August 2025 using Sentinel-2", needs: "ndwi-water-detector" },
  { text: "Check Chilika Lake's water every week through next June", needs: "ndwi-water-detector" },
];

const CHECKPOINTS: { key: string; label: string; matches: (step: string) => boolean }[] = [
  { key: "request", label: "Understanding your request", matches: () => false },
  { key: "models", label: "Evaluating available models", matches: (s) => s === "Evaluating available models" },
  { key: "area", label: "Locating the area", matches: (s) => s.startsWith("Locating ") },
  { key: "collections", label: "Identifying compatible collections", matches: (s) => s === "Identifying compatible collections" },
  { key: "draft", label: "Drafting your workflow", matches: (s) => s === "Drafting your workflow" || s === "Refining your workflow" },
  { key: "storage", label: "Estimating storage needs", matches: (s) => s === "Estimating storage needs" },
];

function reachedCheckpoint(steps: string[]): number {
  return Math.max(0, ...steps.map((step) => CHECKPOINTS.findIndex((c) => c.matches(step))));
}

function stoppedCheckpoint(steps: string[], stoppedAt: string | null | undefined): number {
  const named = CHECKPOINTS.findIndex((c) => c.key === stoppedAt);
  return named >= 0 ? named : reachedCheckpoint(steps);
}

function Checkpoints({ steps, stop }: { steps: string[]; stop?: { at: number; reason: string } }) {
  const current = stop ? stop.at : reachedCheckpoint(steps);
  return (
    <ol role="status" aria-live="polite" className="space-y-1.5 text-sm">
      {CHECKPOINTS.map((checkpoint, i) => {
        const label = checkpoint.key === "draft" && steps.includes("Refining your workflow") ? "Refining your workflow" : checkpoint.label;
        const state = i < current ? "done" : i > current ? "pending" : stop ? "failed" : "active";
        return (
          <li key={checkpoint.key}>
            <div className="flex items-center gap-2">
              <span className="w-4 h-4 shrink-0 flex items-center justify-center" aria-hidden>
                {state === "done" && (
                  <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4 text-brand-600">
                    <path d="m3.5 8.5 3 3 6-7" />
                  </svg>
                )}
                {state === "failed" && (
                  <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" className="w-4 h-4 text-red-600">
                    <path d="m4.5 4.5 7 7m0-7-7 7" />
                  </svg>
                )}
                {state === "active" && <span className="w-4 h-4 rounded-full border-2 border-gray-300 border-t-brand-600 animate-spin" />}
                {state === "pending" && <span className="w-3 h-3 rounded-full border border-gray-300" />}
              </span>
              <span className={state === "done" ? "text-gray-500" : state === "pending" ? "text-gray-400" : "text-gray-900"}>
                {label}
                <span className="sr-only">{{ done: ", done", active: ", in progress", failed: ", stopped here", pending: "" }[state]}</span>
              </span>
            </div>
            {/* the reason sits under the checkpoint it stopped at, lined up with the label past the icon */}
            {state === "failed" && <p className="pl-6 mt-0.5 text-gray-600">{stop!.reason}</p>}
          </li>
        );
      })}
    </ol>
  );
}

export default function WorkflowBuilder({
  onDraft,
  onWorkingChange,
}: {
  // the estimate, when the builder could make one, goes with the draft to the form's storage section
  onDraft: (draft: BuilderDraft, estimate: StorageEstimateResult | null) => void;
  onWorkingChange?: (working: boolean) => void;
}) {
  const [text, setText] = useState("");
  // the conversation lives only here; every turn sends all of it
  const [conversation, setConversation] = useState<BuilderMessage[]>([]);
  const [runId, setRunId] = useState<string | null>(null);
  const [stopped, setStopped] = useState<Stopped | null>(null);
  const [drafted, setDrafted] = useState<Drafted | null>(null);
  // closed until asked for: most people know what they want to type, the examples are there for those who don't
  const [examplesOpen, setExamplesOpen] = useState(false);

  const { data: models } = useModels();
  const registered = new Set((models ?? []).map((m) => m.slug));
  const examples = EXAMPLES.filter((e) => registered.has(e.needs));
  const start = useStartBuilderRun();
  const { data: run } = useBuilderRun(runId);
  const working = start.isPending || !!runId;
  const asked = conversation[conversation.length - 1]?.role === "assistant";
  const steps = run?.id === runId ? run?.steps ?? [] : [];

  useEffect(() => {
    onWorkingChange?.(working);
  }, [working, onWorkingChange]);

  // a finished run is acted on once, then let go
  useEffect(() => {
    if (!run || run.id !== runId || run.status === "queued" || run.status === "running") return;
    setRunId(null);
    const outcome = run.outcome;
    const request = conversation.filter((m) => m.role === "user").map((m) => m.content);
    if (run.status === "failed" || !outcome) {
      setStopped({ request: request.join(" "), steps: run.steps, at: reachedCheckpoint(run.steps), reason: run.error || "Something went wrong" });
      setText(request.join(" "));
      setConversation([]);
      return;
    }
    if (outcome.kind === "question") {
      setConversation((c) => [...c, { role: "assistant", content: outcome.message }]);
      return;
    }
    if (outcome.kind === "cannot") {
      setStopped({ request: request.join(" "), steps: run.steps, at: stoppedCheckpoint(run.steps, outcome.stopped_at), reason: outcome.message || "Something went wrong" });
      // the request comes back into the box, so rephrasing it doesn't mean typing it again
      setText(request.join(" "));
      setConversation([]);
      return;
    }
    if (outcome.draft) onDraft(outcome.draft, outcome.estimate ?? null);
    setDrafted({ request: request[0] ?? "", warnings: outcome.warnings });
    setConversation([]);
  }, [run, runId, onDraft, conversation]);

  async function send() {
    const said = text.trim();
    if (!said || working) return;
    const next: BuilderMessage[] = [...conversation, { role: "user", content: said }];
    setConversation(next);
    setText("");
    setStopped(null);
    setExamplesOpen(false);
    try {
      setRunId((await start.mutateAsync(next)).id);
    } catch (err) {
      // put things back as they were, so nothing typed is lost
      setConversation(conversation);
      setText(said);
      setStopped({ request: null, steps: [], at: 0, reason: (err as Error).message || "Something went wrong" });
    }
  }

  function startOver() {
    setConversation([]);
    setText("");
    setStopped(null);
  }

  // a landed draft is summed up in a line; the filled form below is what's left to review
  if (drafted && !working) {
    return (
      <div className="space-y-1 text-sm">
        <div className="flex items-baseline gap-3">
          <p className="min-w-0 flex-1 truncate">
            <span className="text-gray-500">Drafted from </span>
            <span className="text-gray-900">"{drafted.request}"</span>
          </p>
          <button
            type="button"
            onClick={() => {
              setText(drafted.request);
              setDrafted(null);
            }}
            className="shrink-0 text-gray-500 hover:text-gray-900"
          >
            Change
          </button>
        </div>
        {drafted.warnings.map((w) => (
          <p key={w} className="text-amber-700">
            {w}
          </p>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {conversation.length > 0 && (
        <ul className="space-y-1 text-sm">
          {conversation.map((m, i) => (
            <li key={i} className="flex gap-3">
              <span className="w-16 shrink-0 text-gray-500">{m.role === "user" ? "You" : "Builder"}</span>
              <span className="text-gray-900">{m.content}</span>
            </li>
          ))}
        </ul>
      )}

      {/* a run that stopped short keeps its list, with the request it was for, above the box to rephrase it in */}
      {!working && stopped && (
        <>
          {stopped.request && (
            <p className="flex gap-3 text-sm">
              <span className="w-16 shrink-0 text-gray-500">You</span>
              <span className="text-gray-900">{stopped.request}</span>
            </p>
          )}
          <Checkpoints steps={stopped.steps} stop={{ at: stopped.at, reason: stopped.reason }} />
        </>
      )}

      {/* gone while the builder works: what was sent is shown above, and there's nothing to type until it answers */}
      {!working && (
        <div className="flex gap-2 items-stretch">
          <textarea
            value={text}
            rows={1}
            autoFocus
            onChange={(e) => {
              setText(e.target.value);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            aria-label={asked ? "Answer the builder's question" : "Describe the workflow"}
            className="flex-1 resize-none bg-gray-100 border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:border-brand-500"
          />
          <button
            type="button"
            onClick={send}
            disabled={!text.trim()}
            className="text-sm px-4 py-2 bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white rounded transition-colors"
          >
            {asked ? "Reply" : "Draft"}
          </button>
          {asked && (
            <button type="button" onClick={startOver} className="text-sm px-2 py-2 text-gray-500 hover:text-gray-900">
              Start over
            </button>
          )}
        </div>
      )}

      {working && <Checkpoints steps={steps} />}

      {!working && !stopped && conversation.length === 0 && examples.length > 0 && (
        <div className="text-xs">
          <button
            type="button"
            onClick={() => setExamplesOpen((o) => !o)}
            aria-expanded={examplesOpen}
            className="flex items-center gap-1 text-gray-500 hover:text-gray-900"
          >
            Examples
            <Chevron open={examplesOpen} size="w-3.5 h-3.5" />
          </button>
          {examplesOpen && (
            <ul className="mt-1 space-y-1">
              {examples.map(({ text: example }) => (
                <li key={example}>
                  <button
                    type="button"
                    onClick={() => {
                      setText(example);
                      setExamplesOpen(false);
                    }}
                    className="text-left text-gray-500 hover:text-gray-900"
                  >
                    {example}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
