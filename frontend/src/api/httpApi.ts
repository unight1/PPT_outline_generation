import type {
  Chapter,
  CreateTaskRequest,
  CreateTaskResponse,
  DocumentUploadResponse,
  GenerateSlidesRequest,
  ListTasksResponse,
  Outline,
  OutlineSkeletonSlide,
  RegenerateSlideRequest,
  RegenerateSlideResponse,
  RetrievalDepth,
  Task,
} from '../types/task'

type ApiProblem = {
  error?: {
    code?: string
    message?: string
    details?: Record<string, unknown>
  }
}

function normalizeRetrievalDepth(value: unknown): RetrievalDepth {
  if (value === 'L0' || value === 'L1' || value === 'L2') return value
  const text = String(value ?? '').toUpperCase()
  if (text.endsWith('.L0') || text.endsWith('L0')) return 'L0'
  if (text.endsWith('.L2') || text.endsWith('L2')) return 'L2'
  return 'L1'
}

async function parseError(response: Response): Promise<never> {
  let message = `请求失败（HTTP ${response.status}）`

  try {
    const data = (await response.json()) as ApiProblem
    if (data?.error?.message) {
      message = data.error.message
    }
    const errors = data?.error?.details?.errors
    if (Array.isArray(errors) && errors.length > 0) {
      const first = errors[0] as { loc?: unknown[]; msg?: string }
      const location = Array.isArray(first.loc) ? first.loc.join('.') : ''
      if (first.msg) {
        message = `${message} ${location ? `[${location}] ` : ''}${first.msg}`
      }
    }
  } catch {
    // Keep fallback message when body is not JSON.
  }

  throw new Error(message)
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init?.headers as Record<string, string> ?? {}),
  }
  const token = localStorage.getItem('access_token')
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const response = await fetch(url, {
    headers,
    ...init,
  })

  if (!response.ok) {
    return parseError(response)
  }

  return (await response.json()) as T
}

async function uploadJson<T>(url: string, formData: FormData): Promise<T> {
  const response = await fetch(url, {
    method: 'POST',
    body: formData,
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

export async function listTasks(limit = 10): Promise<ListTasksResponse> {
  return requestJson<ListTasksResponse>(`/api/tasks?limit=${limit}`)
}

export async function uploadTaskDocument(
  taskId: string,
  file: File,
): Promise<DocumentUploadResponse> {
  const formData = new FormData()
  formData.append('file', file)
  return uploadJson<DocumentUploadResponse>(
    `/api/tasks/${taskId}/documents/upload`,
    formData,
  )
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

export async function generateSkeleton(taskId: string): Promise<Task> {
  const result = await requestJson<{ task_id: string; status: Task['status'] }>(
    `/api/tasks/${taskId}/skeleton/generate`,
    {
      method: 'POST',
      body: JSON.stringify({}),
    },
  )

  return getTask(result.task_id)
}

export async function updateSkeleton(
  taskId: string,
  slides: OutlineSkeletonSlide[],
  chapters?: Chapter[],
): Promise<Task> {
  const sanitizedSlides = slides.map((slide) => ({
    slide_id: slide.slide_id,
    title: slide.title,
    intent: slide.intent ?? null,
    user_notes: slide.user_notes ?? null,
    chapter_id: slide.chapter_id ?? null,
  }))
  return requestJson<Task>(`/api/tasks/${taskId}/skeleton`, {
    method: 'PATCH',
    body: JSON.stringify({ slides: sanitizedSlides, chapters }),
  })
}

export async function generateSlides(
  taskId: string,
  options?: GenerateSlidesRequest,
): Promise<Task> {
  const policy = options?.retrieval_policy
  const depth = normalizeRetrievalDepth(policy?.retrieval_depth ?? options?.retrieval_depth)
  const payload: GenerateSlidesRequest = {
    concurrency: options?.concurrency,
    force_refresh: Boolean(options?.force_refresh),
    retrieval_depth: depth,
    tavily_enabled: options?.tavily_enabled,
    retrieval_policy: policy
      ? {
          retrieval_depth: depth,
          tavily_enabled: policy.tavily_enabled,
          prefer_user_doc: policy.prefer_user_doc,
          source_quality: policy.source_quality,
          force_refresh: policy.force_refresh,
          enable_fallback_deepen: policy.enable_fallback_deepen,
        }
      : undefined,
  }
  const result = await requestJson<{ task_id: string; status: Task['status'] }>(
    `/api/tasks/${taskId}/slides/generate`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  )

  return getTask(result.task_id)
}

export async function saveOutline(
  taskId: string,
  outline: Outline,
): Promise<Task> {
  return requestJson<Task>(`/api/tasks/${taskId}/outline`, {
    method: 'PATCH',
    body: JSON.stringify({
      title: outline.title,
      slides: outline.slides,
      evidence_catalog: outline.evidence_catalog,
    }),
  })
}

export async function regenerateSlide(
  taskId: string,
  slideId: string,
  request?: RegenerateSlideRequest,
): Promise<RegenerateSlideResponse> {
  return requestJson<RegenerateSlideResponse>(
    `/api/tasks/${taskId}/slides/${slideId}/regenerate`,
    {
      method: 'POST',
      body: JSON.stringify(request ?? {}),
    },
  )
}

export interface LoginRequest {
  username: string
  password: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  username: string
  role: string
}

export async function login(payload: LoginRequest): Promise<LoginResponse> {
  return requestJson<LoginResponse>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
