import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import { useLive } from "./live";
import type {
  BuilderMessage,
  BuilderRun,
  CollectionInfo,
  ModelInfo,
  TimeseriesResponse,
  Workflow,
  WorkflowItemDetail,
  WorkflowItemPage,
  WorkflowSummary,
  Registered,
} from "./types";

export function useCollections() {
  return useQuery({
    queryKey: ["collections"],
    queryFn: () => api.get<CollectionInfo[]>("/collections"),
  });
}

export function useModels() {
  return useQuery({
    queryKey: ["models"],
    queryFn: () => api.get<ModelInfo[]>("/models"),
  });
}

export function useWorkflows() {
  return useQuery({
    queryKey: ["workflows"],
    queryFn: () => api.get<WorkflowSummary[]>("/workflows"),
  });
}

export function useWorkflow(id: string) {
  const live = useLive((s) => s.connected);
  return useQuery({
    queryKey: ["workflows", id],
    queryFn: () => api.get<Workflow>(`/workflows/${id}`),
    enabled: !!id,
    refetchInterval: (query) => {
      const wf = query.state.data;
      if (live || !wf) return false;
      if (wf.status === "running") return 3000;
      return false;
    },
  });
}

export function useCreateWorkflow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: unknown) => api.post<Workflow>("/workflows", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["workflows"] }),
  });
}

export function useDeleteWorkflow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/workflows/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["workflows"] }),
  });
}

export function useRunWorkflow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post(`/workflows/${id}/run`),
    onSuccess: (_d, id) => qc.invalidateQueries({ queryKey: ["workflows", id] }),
  });
}

export function useFetchNow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<Workflow>(`/workflows/${id}/fetch-now`),
    onSuccess: (_d, id) => qc.invalidateQueries({ queryKey: ["workflows", id] }),
  });
}

const ITEMS_PAGE_SIZE = 50;

export function useWorkflowItems(
  workflowId: string,
  severity?: string,
  isRunning = false,
) {
  const live = useLive((s) => s.connected);
  return useInfiniteQuery({
    queryKey: ["workflow-items", workflowId, severity],
    queryFn: ({ pageParam = 1 }) => {
      const params = new URLSearchParams({ page: String(pageParam), page_size: String(ITEMS_PAGE_SIZE) });
      if (severity) params.set("severity", severity);
      return api.get<WorkflowItemPage>(`/workflows/${workflowId}/items?${params}`);
    },
    initialPageParam: 1,
    getNextPageParam: (last) => last.page < last.pages ? last.page + 1 : undefined,
    enabled: !!workflowId,
    refetchInterval: isRunning && !live ? 3000 : false,
    // switching the severity filter is a new query; keep the current rows up until its results arrive,
    // otherwise the table empties for a moment and the page jumps by its height
    placeholderData: keepPreviousData,
  });
}

export function useWorkflowItem(workflowId: string, itemId: string) {
  return useQuery({
    queryKey: ["workflow-item", workflowId, itemId],
    queryFn: () =>
      api.get<WorkflowItemDetail>(`/workflows/${workflowId}/items/${itemId}`),
    enabled: !!workflowId && !!itemId,
  });
}

export function useWorkflowTimeseries(workflowId: string) {
  return useQuery({
    queryKey: ["workflow-timeseries", workflowId],
    queryFn: () => api.get<TimeseriesResponse>(`/workflows/${workflowId}/timeseries`),
    enabled: !!workflowId,
  });
}

export function useRegistered(kind: "model" | "provider") {
  const live = useLive((s) => s.connected);
  return useQuery({
    queryKey: ["registered", kind],
    queryFn: () => api.get<Registered[]>(`/${kind}s/registered`),
    // a queued smoke test flips is_enabled from the worker, so keep this fresh when nothing announces it
    refetchInterval: live ? false : 4000,
  });
}

export function useStartBuilderRun() {
  return useMutation({
    mutationFn: (conversation: BuilderMessage[]) => api.post<BuilderRun>("/builder/runs", { conversation }),
  });
}

export function useBuilderRun(id: string | null) {
  const live = useLive((s) => s.connected);
  return useQuery({
    queryKey: ["builder-run", id],
    queryFn: () => api.get<BuilderRun>(`/builder/runs/${id}`),
    enabled: !!id,
    // the worker's steps and answer arrive as live changes; poll only when nothing announces them
    refetchInterval: (query) => {
      const run = query.state.data;
      return !live && (!run || run.status === "queued" || run.status === "running") ? 2000 : false;
    },
  });
}
