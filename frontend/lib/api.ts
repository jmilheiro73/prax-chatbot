/** Chamadas ao back, fora o stream do chat (esse fica em `page.tsx`, com o `readSse`). */

import type { TranscriptMessage } from "./reducer";

export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface ThreadEntry {
  thread_id: string;
  title: string;
  last_used_at: string;
}

export interface ThreadSnapshot {
  checkpoint_alive: boolean;
  summary: string | null;
  transcript: TranscriptMessage[];
}

export type Feedback = "up" | "down" | null;

export interface KnowledgeDocument {
  id: string;
  name: string;
  version: number;
  status: "queued" | "chunking" | "embedding" | "ready" | "error";
  error: string | null;
  chunk_count: number;
  reused_chunks: number;
}

export type MemoryType = "fact" | "profile";

export interface UserMemory {
  id: string;
  type: MemoryType;
  content: string;
}

async function request(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(`${API}${path}`, init);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response;
}

function jsonBody(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export async function fetchThreads(): Promise<ThreadEntry[]> {
  return (await (await request("/agent/threads")).json()).threads;
}

export async function fetchSnapshot(id: string): Promise<ThreadSnapshot> {
  return (await request(`/agent/threads/${id}`)).json();
}

export async function deleteThread(id: string): Promise<void> {
  await request(`/agent/threads/${id}`, { method: "DELETE" });
}

export async function sendFeedback(threadId: string, runId: string, value: Feedback): Promise<void> {
  await request(`/agent/threads/${threadId}/feedback`, jsonBody("POST", { run_id: runId, value }));
}

export async function fetchDocuments(): Promise<KnowledgeDocument[]> {
  return (await (await request("/knowledge/documents")).json()).documents;
}

export async function submitDocument(name: string, content: string): Promise<void> {
  await request("/knowledge/documents", jsonBody("POST", { name, content }));
}

export async function deleteDocument(id: string): Promise<void> {
  await request(`/knowledge/documents/${id}`, { method: "DELETE" });
}

export async function fetchMemories(): Promise<UserMemory[]> {
  return (await (await request("/memories")).json()).memories;
}

export async function createMemory(type: MemoryType, content: string): Promise<void> {
  await request("/memories", jsonBody("POST", { type, content }));
}

export async function updateMemory(id: string, content: string): Promise<void> {
  await request(`/memories/${id}`, jsonBody("PATCH", { content }));
}

export async function deleteMemory(id: string): Promise<void> {
  await request(`/memories/${id}`, { method: "DELETE" });
}
