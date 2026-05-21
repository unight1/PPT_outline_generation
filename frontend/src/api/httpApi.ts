import type {
  CreateTaskRequest,
  CreateTaskResponse,
  Task,
} from '../types/task'

type ApiProblem = {
  error?: {
    code?: string
    message?: string
    details?: Record<string, unknown>
  }
}

async function parseError(response: Response): Promise<never> {
  let message = `请求失败（HTTP ${response.status}）`

  try {
    const data = (await response.json()) as ApiProblem
    if (data?.error?.message) {
      message = data.error.message
    }
  } catch {
    // Keep fallback message when body is not JSON.
  }

  throw new Error(message)
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  })

  if (!response.ok) {
    return parseError(response)
  }

  return (await response.json()) as T
}

export async function createTask(
  request: CreateTaskRequest,
): Promise<CreateTaskResponse> {
  return requestJson<CreateTaskResponse>('/api/tasks', {
    method: 'POST',
    body: JSON.stringify(request),
  })
}

export async function getTask(taskId: string): Promise<Task> {
  return requestJson<Task>(`/api/tasks/${taskId}`)
}

export async function submitClarification(
  taskId: string,
  answers: Record<string, string>,
): Promise<Task> {
  const payload = {
    answers: Object.entries(answers).map(([question_id, answer]) => ({
      question_id,
      answer,
    })),
    submitted: true,
  }

  return requestJson<Task>(`/api/tasks/${taskId}/clarification`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export async function generateOutline(taskId: string): Promise<Task> {
  const result = await requestJson<{ task_id: string; status: Task['status'] }>(
    `/api/tasks/${taskId}/generate`,
    {
      method: 'POST',
      body: JSON.stringify({}),
    },
  )

  // Keep UI data model simple: immediately fetch latest full snapshot.
  return getTask(result.task_id)
}

