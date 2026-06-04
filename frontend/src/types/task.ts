export type TaskStatus =
  | 'pending'
  | 'clarifying'
  | 'generating'
  | 'done'
  | 'failed'

export type RetrievalDepth = 'L0' | 'L1' | 'L2'

export type WorkflowPhase =
  | 'idle'
  | 'skeleton_llm'
  | 'skeleton_ready'
  | 'retrieving_page'
  | 'llm_page'
  | 'assembling'
  | 'saving'
  | 'regenerating_slide'
  | 'done'
  | 'failed'

export interface CreateTaskRequest {
  topic: string
  source_type?: 'short_topic' | 'long_document'
  audience?: string
  duration_minutes?: number
  language?: string
  retrieval_depth?: RetrievalDepth
  raw_notes?: string
  document_text?: string
  document_title?: string
}

export interface CreateTaskResponse {
  task_id: string
  status: TaskStatus
  created_at: string
}

export interface ClarificationQuestion {
  question_id: string
  prompt: string
  answer: string | null
}

export interface Clarification {
  questions: ClarificationQuestion[]
  submitted: boolean
}

export interface Progress {
  phase: WorkflowPhase
  current: number | null
  total: number | null
  message?: string
  percent: number | null

  slide_id?: string | null
  completed?: number
  failed?: number
}

export interface OutlineSkeletonSlide {
  slide_id: string
  title: string
  intent: string | null
  user_notes: string | null
}

export interface Bullet {
  bullet_id: string
  text: string
  evidence_ids: string[]
}

export interface Slide {
  slide_id: string
  title: string
  key_message?: string | null        // B1: 本页核心结论一句话
  bullets: Bullet[]
  speaker_notes: string | null
  visual_suggestion?: string | null  // B1: 建议配图/图表类型
  takeaway?: string | null           // B1: 听众行动建议或关键启示
}

export interface Evidence {
  evidence_id: string
  snippet: string
  source_id: string
  locator: string
  score: number | null
  confidence: number | null
}

export interface Outline {
  title: string
  slides: Slide[]
  evidence_catalog: Evidence[]
  page_evidence_map?: Array<{
    slide_id: string
    slide_title: string
    evidence_trace: Array<Record<string, unknown>>
  }>
  meta: {
    retrieval_depth?: RetrievalDepth
    generated_at?: string
    schema_version?: string
    [key: string]: unknown
  }
}

export interface TaskError {
  code: string
  message: string
  details?: Record<string, unknown>
}

export interface Task {
  task_id: string
  schema_version?: string
  status: TaskStatus
  created_at: string
  updated_at: string
  clarification: Clarification | null
  outline_skeleton: OutlineSkeletonSlide[] | null
  outline: Outline | null
  progress: Progress | null
  error: TaskError | null
}

export interface RegenerateSlideRequest {
  user_instruction?: string
}

export interface RegenerateSlideResponse {
  task_id: string
  status: TaskStatus
  accepted: boolean
  slide_id: string
}

export interface GenerateSlidesRequest {
  concurrency?: 1 | 2 | 3
  force_refresh?: boolean
  retrieval_depth?: RetrievalDepth
  tavily_enabled?: boolean
}

export type SlideGenerationErrorCode =
  | 'LLM_ERROR'
  | 'RETRIEVAL_ERROR'
  | 'TAVILY_ERROR'
  | 'TIMEOUT'
  | 'INTERNAL_ERROR'
  | 'GENERATION_TIMEOUT'
  | 'RETRIEVAL_UNAVAILABLE'
  | string
