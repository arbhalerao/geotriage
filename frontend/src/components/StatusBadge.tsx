import type { ReactNode } from "react";
import { TONE_TEXT, labelOf, toneOf, type Tone } from "../status";

export default function StatusBadge({ status }: { status: string }) {
  return <span className={`whitespace-nowrap text-sm font-medium ${TONE_TEXT[toneOf(status)]}`}>{labelOf(status)}</span>;
}

export function ToneText({ tone, children }: { tone: Tone; children: ReactNode }) {
  return <span className={`whitespace-nowrap text-sm font-medium ${TONE_TEXT[tone]}`}>{children}</span>;
}
