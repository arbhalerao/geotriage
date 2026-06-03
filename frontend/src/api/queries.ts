import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type {
  Bookmark,
  CollectionInfo,
  ModelInfo,
  Review,
  TimeseriesResponse,
  Workflow,
  WorkflowItemDetail,
  WorkflowItemPage,
  WorkflowSummary,
  WorkerStatus,
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
  return useQuery({
    queryKey: ["workflows", id],
    queryFn: () => api.get<Workflow>(`/workflows/${id}`),
    enabled: !!id,
    refetchInterval: (query) => {
      const wf = query.state.data;
      if (!wf) return false;
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
    refetchInterval: isRunning ? 3000 : false,
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

export function useUpsertReview(workflowId: string, itemId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { review_status: string; notes?: string }) =>
      api.put<Review>(`/workflows/${workflowId}/items/${itemId}/review`, data),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["workflow-item", workflowId, itemId] }),
  });
}

export function useAddBookmark(workflowId: string, itemId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api.post<Bookmark>(`/workflows/${workflowId}/items/${itemId}/bookmark`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["workflow-item", workflowId, itemId] });
      qc.invalidateQueries({ queryKey: ["workflow-items", workflowId] });
    },
  });
}

export function useRemoveBookmark(workflowId: string, itemId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api.delete(`/workflows/${workflowId}/items/${itemId}/bookmark`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["workflow-item", workflowId, itemId] });
      qc.invalidateQueries({ queryKey: ["workflow-items", workflowId] });
    },
  });
}

export function useWorkflowTimeseries(workflowId: string) {
  return useQuery({
    queryKey: ["workflow-timeseries", workflowId],
    queryFn: () => api.get<TimeseriesResponse>(`/workflows/${workflowId}/timeseries`),
    enabled: !!workflowId,
  });
}

export function useWorkerStatus(enabled = true) {
  return useQuery({
    queryKey: ["worker-status"],
    queryFn: () => api.get<WorkerStatus>("/worker/status"),
    enabled,
    refetchInterval: 5000,
  });
}

export function useRegistered(kind: "model" | "provider") {
  return useQuery({
    queryKey: ["registered", kind],
    queryFn: () => api.get<Registered[]>(`/${kind}s/registered`),
    // a queued smoke test flips is_enabled from the worker, so keep this fresh
    refetchInterval: 4000,
  });
}
