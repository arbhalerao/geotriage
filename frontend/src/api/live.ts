import { useEffect } from "react";
import { useQueryClient, type QueryClient, type QueryKey } from "@tanstack/react-query";
import { create } from "zustand";

// what the database triggers announce; see backend/api/live.py
type Change =
  | { topic: "workflow"; id: string }
  | { topic: "workflow_item"; id: string; workflow_id: string }
  | { topic: "model_run"; id: string; workflow_item_id: string; workflow_id: string | null }
  | { topic: "registry"; kind: "model" | "provider" }
  | { topic: "builder_run"; id: string }
  | { topic: "queue" };

type LiveMessage = { type: "changes"; changes: Change[] } | { type: "resync" };

const RECONNECT_MIN_MS = 1_000;
const RECONNECT_MAX_MS = 30_000;

// queries poll only while this is false, so a dropped socket degrades to the old behaviour
export const useLive = create<{ connected: boolean }>(() => ({ connected: false }));

function keysFor(change: Change): QueryKey[] {
  switch (change.topic) {
    case "workflow":
      // prefix match: the list and the detail view both
      return [["workflows"]];
    case "workflow_item":
      return [
        ["workflows", change.workflow_id], // its item counts
        ["workflow-items", change.workflow_id],
        ["workflow-timeseries", change.workflow_id],
        ["workflow-item", change.workflow_id, change.id],
      ];
    case "model_run":
      return change.workflow_id ? [["workflow-item", change.workflow_id, change.workflow_item_id]] : [];
    case "registry":
      // a provider's collections decide which models are compatible, so both catalogues move
      return change.kind === "model"
        ? [["registered", "model"], ["models"]]
        : [["registered", "provider"], ["collections"], ["models"]];
    case "builder_run":
      return [["builder-run", change.id]];
    case "queue":
      // nothing on screen reads the queue yet; the Infra page will once its backend exists
      return [];
  }
}

function invalidate(qc: QueryClient, changes: Change[]) {
  // a batch names many rows under the same few keys; refetch each key once
  const keys = new Map<string, QueryKey>();
  for (const change of changes) {
    for (const key of keysFor(change)) keys.set(JSON.stringify(key), key);
  }
  for (const key of keys.values()) qc.invalidateQueries({ queryKey: key });
}

function liveUrl() {
  const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${window.location.host}/api/live`;
}

export function useLiveUpdates() {
  const qc = useQueryClient();

  useEffect(() => {
    let socket: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let delay = RECONNECT_MIN_MS;
    let stopped = false;

    const connect = () => {
      socket = new WebSocket(liveUrl());

      socket.onopen = () => {
        delay = RECONNECT_MIN_MS;
        useLive.setState({ connected: true });
        // nothing that changed before this socket opened was announced to it
        qc.invalidateQueries();
      };

      socket.onmessage = (event) => {
        const message = JSON.parse(event.data) as LiveMessage;
        if (message.type === "resync") qc.invalidateQueries();
        else invalidate(qc, message.changes);
      };

      socket.onclose = () => {
        // a socket closed by cleanup must not flip the state of the one that replaced it
        if (stopped) return;
        useLive.setState({ connected: false });
        retry = setTimeout(connect, delay);
        delay = Math.min(delay * 2, RECONNECT_MAX_MS);
      };
    };

    connect();
    return () => {
      stopped = true;
      clearTimeout(retry);
      socket?.close();
      useLive.setState({ connected: false });
    };
  }, [qc]);
}
