export type TaskStatus =
  | 'pending'
  | 'clarifying'
  | 'generating'
  | 'done'
  | 'failed'

export type RetrievalDepth = 'L0' | 'L1' | 'L2'
export type SourceQuality = 'low' | 'medium' | 'high'
export type AttachmentStatus = 'pending' | 'ready' | 'failed'
export type DocumentAnalysisStatus = 'pending' | 'running' | 'done' | 'failed'

export type WorkflowPhase =
  | 'idle'
  | 'document_analysis'
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
  target_pages?: number
  target_pages_min?: number
  target_pages_max?: number
  desired_chapters?: string
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

export interface DocumentProfile {
  summary?: string
  key_points?: string[]
  suggested_focus?: string | null
  segments?: string[]
  segment_count?: number
  char_count?: number
  keywords?: string[]
  [key: string]: unknown
}

export interface Attachment {
  document_id: string
  filename: string
  status: AttachmentStatus
  chunk_count: number | null
}

export interface RetrievalPolicy {
  retrieval_depth?: RetrievalDepth
  tavily_enabled?: boolean
  prefer_user_doc?: boolean
  source_quality?: SourceQuality
  force_refresh?: boolean
  enable_fallback_deepen?: boolean
}

export interface TaskRuntime {
  document_analysis_status?: DocumentAnalysisStatus | null
  retrieval_policy?: RetrievalPolicy | null
  [key: string]: unknown
}

export interface TaskInput {
  topic?: string
  source_type?: 'short_topic' | 'long_document'
  retrieval_depth?: RetrievalDepth
  document_title?: string | null
  document_profile?: DocumentProfile | null
  attachments?: Attachment[]
  [key: string]: unknown
}

export interface OutlineSkeletonSlide {
  slide_id: string
  title: string
  intent: string | null
  user_notes: string | null
  chapter_id?: string | null
}

export interface Chapter {
  chapter_id: string
  title: string
  slide_ids: string[]
}

export interface Bullet {
  bullet_id: string
  text: string
  evidence_ids: string[]
}

export interface Slide {
  slide_id: string
  title: string
  chapter_id?: string | null
  key_message?: string | null        // B1: 本页核心结论一句话
  bullets: Bullet[]
  speaker_notes: string | null
  visual_suggestion?: string | null  // B1: 建议配图/图表类型
  takeaway?: string | null           // B1: 听众行动建议或关键启示
  generation_status?: 'done' | 'failed'
  error?: {
    code?: string
    message?: string
  }
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
  chapters?: Chapter[]
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
  outline_skeleton_chapters?: Chapter[] | null
  outline: Outline | null
  progress: Progress | null
  error: TaskError | null
  input?: TaskInput
  runtime?: TaskRuntime | null
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
  retrieval_policy?: RetrievalPolicy
}

export interface TaskListItem {
  task_id: string
  status: TaskStatus
  updated_at: string
  created_at?: string
  input?: {
    topic?: string
    source_type?: 'short_topic' | 'long_document'
    [key: string]: unknown
  }
}

export interface ListTasksResponse {
  tasks: TaskListItem[]
  total: number
}

export interface DocumentUploadResponse {
  document_id: string
  filename: string
  status: AttachmentStatus
  chunk_count: number | null
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

export interface EvalCase {
  eval_id: string
  topic: string
  source_type: string
  document_text: string | null
  expected_depth: string
  constraints: string[]
  priority: string
  status: string
  task_id: string | null
  score: number | null
  evaluator: string | null
  evidence_coverage: number | null
  notes: string | null
  created_at: string | null
  updated_at: string | null
}
