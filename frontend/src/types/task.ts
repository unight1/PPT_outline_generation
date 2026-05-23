export type TaskStatus =
  | 'pending'
  | 'clarifying'
  | 'generating'
  | 'done'
  | 'failed'

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

export interface Progress {
  phase: WorkflowPhase
  current: number | null
  total: number | null
  message?: string
  percent: number | null
}

export interface OutlineSkeletonSlide {
  slide_id: string
  title: string
  intent: string | null
  user_notes: string | null
}

export type RetrievalDepth = 'L0' | 'L1' | 'L2'

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

export interface Bullet {
  bullet_id: string
  text: string
  evidence_ids: string[]
}

export interface Slide {
  slide_id: string
  title: string
  bullets: Bullet[]
  speaker_notes: string | null
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
  outline_skeleton?: OutlineSkeletonSlide[] | null
  outline: Outline | null
  progress?: Progress | null
  error: TaskError | null
}
