import { useEffect, useState } from "react";
import { useBuilderRun, useModels, useStartBuilderRun } from "../api/queries";
import Chevron from "./Chevron";
import type { BuilderDraft, BuilderMessage } from "../api/types";

// a failure is dismissible like any form error; a refusal is something to rephrase
type Notice = { kind: "error" | "cannot"; text: string };

// what the landed draft came from, and what the builder assumed or wants reconsidered
type Drafted = { request: string; message: string; warnings: string[] };

// said in different ways on purpose: a question, a plain request, a named satellite, relative dates;
// each is shown only while the detector it needs is registered, since models come and go without a release
const EXAMPLES: { text: string; needs: string }[] = [
  { text: "Watch for flooding around Dhaka every day until the end of October", needs: "ndwi-water-detector" },
  { text: "How hot did Phoenix, Arizona get in July 2025?", needs: "lst-detector" },
  { text: "Track the water in Lake Urmia during 2023", needs: "ndwi-water-detector" },
  { text: "Map water around Patna in August 2025 using Sentinel-2", needs: "ndwi-water-detector" },
  { text: "Check Chilika Lake's water every week through next June", needs: "ndwi-water-detector" },
];

const DISMISS =
  "shrink-0 w-6 h-6 flex items-center justify-center rounded text-gray-500 hover:text-gray-800 hover:bg-white/70 transition-colors";

export default function WorkflowBuilder({
  onDraft,
  onWorkingChange,
}: {
  onDraft: (draft: BuilderDraft) => void;
  onWorkingChange?: (working: boolean) => void;
}) {
  const [text, setText] = useState("");
  // the conversation lives only here; every turn sends all of it
  const [conversation, setConversation] = useState<BuilderMessage[]>([]);
  const [runId, setRunId] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
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
      setNotice({ kind: "error", text: `The builder stopped: ${run.error ?? "no answer"}` });
      setText(request.join(" "));
      setConversation([]);
      return;
    }
    if (outcome.kind === "question") {
      setConversation((c) => [...c, { role: "assistant", content: outcome.message }]);
      return;
    }
    if (outcome.kind === "cannot") {
      setNotice({ kind: "cannot", text: outcome.message });
      // the request comes back into the box, so rephrasing it doesn't mean typing it again
      setText(request.join(" "));
      setConversation([]);
      return;
    }
    if (outcome.draft) onDraft(outcome.draft);
    setDrafted({ request: request[0] ?? "", message: outcome.message, warnings: outcome.warnings });
    setConversation([]);
  }, [run, runId, onDraft, conversation]);

  async function send() {
    const said = text.trim();
    if (!said || working) return;
    const next: BuilderMessage[] = [...conversation, { role: "user", content: said }];
    setConversation(next);
    setText("");
    setNotice(null);
    setExamplesOpen(false);
    try {
      setRunId((await start.mutateAsync(next)).id);
    } catch (err) {
      // put things back as they were, so nothing typed is lost
      setConversation(conversation);
      setText(said);
      setNotice({ kind: "error", text: `The request failed: ${(err as Error).message}` });
    }
  }

  function startOver() {
    setConversation([]);
    setText("");
    setNotice(null);
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
        {drafted.message && <p className="text-gray-600">{drafted.message}</p>}
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

      {/* gone while the builder works: what was sent is shown above, and there's nothing to type until it answers */}
      {!working && (
        <div className="flex gap-2 items-stretch">
          <textarea
            value={text}
            rows={1}
            autoFocus
            onChange={(e) => {
              setText(e.target.value);
              setNotice(null);
            }}
            // going back to the input means a failure has been read
            onFocus={() => setNotice(null)}
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

      {working && (
        <p role="status" aria-live="polite" className="min-h-5 flex items-center gap-2 text-sm">
          <span className="w-4 h-4 rounded-full border-2 border-gray-300 border-t-brand-600 animate-spin" aria-hidden />
          <span className="text-blue-700">{steps[steps.length - 1] ?? "Waiting for the model"}</span>
        </p>
      )}

      {!working && notice && (
        // a refusal needs attention, a failure is a failure: the one palette, amber and red
        <div
          role="alert"
          className={`flex items-start gap-3 rounded border px-3 py-2 text-sm ${notice.kind === "error" ? "border-red-200 bg-red-50/60" : "border-amber-200 bg-amber-50/60"}`}
        >
          <p className={`flex-1 ${notice.kind === "error" ? "text-red-800" : "text-amber-800"}`}>{notice.text}</p>
          <button type="button" onClick={() => setNotice(null)} aria-label="Dismiss" className={DISMISS}>
            ×
          </button>
        </div>
      )}

      {!working && !notice && conversation.length === 0 && examples.length > 0 && (
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
