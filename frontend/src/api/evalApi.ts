import type { EvalCase } from '../types/task'

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init?.headers as Record<string, string> ?? {}),
  }
  const token = localStorage.getItem('access_token')
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  const resp = await fetch(url, { headers, ...init })
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}))
    throw new Error((body as { error?: { message?: string } })?.error?.message ?? `HTTP ${resp.status}`)
  }
  return resp.json()
}

export async function listEvalCases(): Promise<EvalCase[]> {
  const data = await requestJson<{ items: EvalCase[] }>('/api/eval')
  return data.items ?? []
}

export async function createEvalCase(payload: Partial<EvalCase>): Promise<EvalCase> {
  return requestJson<EvalCase>('/api/eval', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function getEvalCase(evalId: string): Promise<EvalCase> {
  return requestJson<EvalCase>(`/api/eval/${evalId}`)
}

export async function updateEvalCase(evalId: string, payload: Partial<EvalCase>): Promise<EvalCase> {
  return requestJson<EvalCase>(`/api/eval/${evalId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export async function deleteEvalCase(evalId: string): Promise<void> {
  await requestJson(`/api/eval/${evalId}`, { method: 'DELETE' })
}

export async function scoreEvalCase(evalId: string, payload: Record<string, unknown>): Promise<EvalCase> {
  return requestJson<EvalCase>(`/api/eval/${evalId}/score`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export interface EvalStats {
  total: number
  scored: number
  average_score: number | null
  by_priority: Record<string, number>
  by_status: Record<string, number>
}

export async function getEvalStats(): Promise<EvalStats> {
  return requestJson<EvalStats>('/api/eval/stats/summary')
}
