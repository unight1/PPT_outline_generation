import type {
  Chapter,
  DocumentUploadResponse,
  CreateTaskRequest,
  CreateTaskResponse,
  GenerateSlidesRequest,
  ListTasksResponse,
  Outline,
  OutlineSkeletonSlide,
  RegenerateSlideRequest,
  RegenerateSlideResponse,
  Task,
} from '../types/task'
import { mockTaskClarifying, mockTaskDone } from '../mocks/mockTask'

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

let currentTask: Task | null = null
let pollCount = 0
let uploadedCount = 0

export async function createTask(
  request: CreateTaskRequest,
): Promise<CreateTaskResponse> {
  await sleep(600)

  currentTask = {
    ...mockTaskClarifying,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    input: {
      topic: request.topic,
      source_type: request.source_type ?? 'short_topic',
      retrieval_depth: request.retrieval_depth ?? 'L1',
      target_pages_min: request.target_pages_min ?? 8,
      target_pages_max: request.target_pages_max ?? 12,
      desired_chapters: request.desired_chapters,
      document_title: request.document_title,
      document_profile:
        request.source_type === 'long_document'
          ? {
              summary: 'Mock 文档摘要：已识别长文档主题与核心观点。',
              key_points: ['核心问题', '方案路径', '预期价值'],
              char_count: request.document_text?.length ?? 0,
            }
          : null,
      attachments:
        request.source_type === 'long_document' && request.document_text?.trim()
          ? [
              {
                document_id: 'doc_mock_body',
                filename: `${request.document_title || 'document'}.md`,
                status: 'ready',
                chunk_count: 3,
              },
            ]
          : [],
    },
    runtime: {
      document_analysis_status:
        request.source_type === 'long_document' ? 'done' : null,
      retrieval_policy: {
        retrieval_depth: request.retrieval_depth ?? 'L1',
        tavily_enabled: true,
        prefer_user_doc: request.source_type === 'long_document',
        source_quality: 'medium',
        force_refresh: false,
        enable_fallback_deepen: false,
      },
    },
  }

  console.log('Mock create task request:', request)

  return {
    task_id: currentTask.task_id,
    status: 'clarifying',
    created_at: currentTask.created_at,
  }
}

export async function getTask(taskId: string): Promise<Task> {
  await sleep(600)

  if (taskId === 'mock-history-1') {
    currentTask = {
      ...mockTaskDone,
      task_id: taskId,
      created_at: new Date(Date.now() - 7200_000).toISOString(),
      updated_at: new Date(Date.now() - 3600_000).toISOString(),
      input: {
        topic: '历史任务示例',
        source_type: 'short_topic',
        retrieval_depth: 'L1',
        attachments: [],
      },
      runtime: {
        retrieval_policy: {
          retrieval_depth: 'L1',
          tavily_enabled: true,
          prefer_user_doc: false,
          source_quality: 'medium',
          force_refresh: false,
          enable_fallback_deepen: false,
        },
      },
    }
    return currentTask
  }

  if (!currentTask || currentTask.task_id !== taskId) {
    throw new Error('任务不存在')
  }

  if (currentTask.status === 'generating') {
    pollCount += 1

    if (currentTask.progress?.phase === 'skeleton_llm' && pollCount >= 2) {
      const skeleton = buildMockSkeleton()
      currentTask = {
        ...currentTask,
        status: 'pending',
        outline_skeleton: skeleton,
        updated_at: new Date().toISOString(),
        progress: {
          phase: 'skeleton_ready',
          current: null,
          total: skeleton.length,
          message: '骨架已生成，请确认每页主题。',
          percent: null,
        },
      }
    } else if (currentTask.progress?.phase !== 'skeleton_llm') {
      const total =
        currentTask.outline_skeleton?.length ?? mockTaskDone.outline?.slides.length ?? 0

      const completed = Math.min(pollCount, total)
      const partialSlides = mockTaskDone.outline?.slides.slice(0, completed) ?? []
      const currentSlide = partialSlides[partialSlides.length - 1]

      if (completed >= total) {
        currentTask = {
          ...mockTaskDone,
          task_id: taskId,
          created_at: currentTask.created_at,
          updated_at: new Date().toISOString(),
          outline_skeleton:
            currentTask.outline_skeleton ?? mockTaskDone.outline_skeleton,
          outline: mockTaskDone.outline
            ? {
                ...mockTaskDone.outline,
                meta: {
                  ...mockTaskDone.outline.meta,
                  partial: false,
                  completed_pages: total,
                  failed_pages: 0,
                  total_pages: total,
                },
              }
            : null,
          progress: {
            phase: 'done',
            current: total,
            total,
            message: '全部页面已生成完成。',
            percent: 100,
            slide_id: currentSlide?.slide_id ?? null,
            completed: total,
            failed: 0,
          },
        }
      } else {
        currentTask = {
          ...currentTask,
          status: 'generating',
          updated_at: new Date().toISOString(),
          outline: mockTaskDone.outline
            ? {
                ...mockTaskDone.outline,
                slides: partialSlides,
                meta: {
                  ...mockTaskDone.outline.meta,
                  partial: true,
                  completed_pages: completed,
                  failed_pages: 0,
                  total_pages: total,
                },
              }
            : currentTask.outline,
          progress: {
            phase: 'llm_page',
            current: completed,
            total,
            message: `已完成 ${completed} 页，正在生成第 ${completed + 1}/${total} 页。`,
            percent: total ? Math.round((completed / total) * 100) : null,
            slide_id: currentSlide?.slide_id ?? null,
            completed,
            failed: 0,
          },
        }
      }
    }
  }

  return currentTask
}

export async function listTasks(): Promise<ListTasksResponse> {
  await sleep(300)
  const tasks = currentTask
    ? [
        {
          task_id: currentTask.task_id,
          status: currentTask.status,
          updated_at: currentTask.updated_at,
          created_at: currentTask.created_at,
          input: {
            topic: currentTask.input?.topic ?? '当前 Mock 任务',
            source_type: currentTask.input?.source_type ?? 'short_topic',
          },
        },
        {
          task_id: 'mock-history-1',
          status: 'done' as const,
          updated_at: new Date(Date.now() - 3600_000).toISOString(),
          input: { topic: '历史任务示例', source_type: 'short_topic' as const },
        },
      ]
    : [
        {
          task_id: 'mock-history-1',
          status: 'done' as const,
          updated_at: new Date(Date.now() - 3600_000).toISOString(),
          input: { topic: '历史任务示例', source_type: 'short_topic' as const },
        },
      ]
  return { tasks, total: tasks.length }
}

export async function uploadTaskDocument(
  taskId: string,
  file: File,
): Promise<DocumentUploadResponse> {
  await sleep(500)
  if (!currentTask || currentTask.task_id !== taskId) {
    throw new Error('任务不存在')
  }
  uploadedCount += 1
  const attachment = {
    document_id: `mock_doc_${uploadedCount}`,
    filename: file.name,
    status: 'ready' as const,
    chunk_count: 3,
  }
  currentTask = {
    ...currentTask,
    input: {
      ...(currentTask.input ?? {}),
      attachments: [...(currentTask.input?.attachments ?? []), attachment],
    },
    updated_at: new Date().toISOString(),
  }
  return attachment
}

export async function submitClarification(
  taskId: string,
  answers: Record<string, string>,
): Promise<Task> {
  await sleep(600)

  if (!currentTask || currentTask.task_id !== taskId) {
    throw new Error('任务不存在')
  }

  currentTask = {
    ...currentTask,
    status: 'pending',
    updated_at: new Date().toISOString(),
    clarification: {
      submitted: true,
      questions:
        currentTask.clarification?.questions.map((question) => ({
          ...question,
          answer: answers[question.question_id] ?? question.answer,
        })) ?? [],
    },
    progress: {
      phase: 'idle',
      current: null,
      total: null,
      message: '澄清已提交，可以生成骨架。',
      percent: null,
    },
  }

  return currentTask
}

export async function generateOutline(taskId: string): Promise<Task> {
  await sleep(600)

  if (!currentTask || currentTask.task_id !== taskId) {
    throw new Error('任务不存在')
  }

  pollCount = 0

  currentTask = {
    ...currentTask,
    status: 'generating',
    updated_at: new Date().toISOString(),
  }

  return currentTask
}

function buildMockSkeleton(): OutlineSkeletonSlide[] {
  const base = [
    {
      slide_id: 's1',
      title: '问题背景与目标',
      intent: '说明为什么要关注该主题',
      user_notes: null,
    },
    {
      slide_id: 's2',
      title: '现状分析与关键挑战',
      intent: '梳理现状、痛点和约束',
      user_notes: null,
    },
    {
      slide_id: 's3',
      title: '方案设计与核心路径',
      intent: '说明系统方案和实现思路',
      user_notes: null,
    },
    {
      slide_id: 's4',
      title: '落地计划与预期收益',
      intent: '说明如何实施以及带来的价值',
      user_notes: null,
    },
    {
      slide_id: 's5',
      title: '风险边界与下一步行动',
      intent: '说明限制、风险和后续计划',
      user_notes: null,
    },
  ]
  const minPages = Number(currentTask?.input?.target_pages_min ?? base.length)
  const maxPages = Number(currentTask?.input?.target_pages_max ?? minPages)
  const targetPages = Math.floor((minPages + maxPages) / 2)
  return Array.from({ length: Math.max(3, Math.min(30, targetPages)) }, (_, index) => (
    base[index] ?? {
      slide_id: `s${index + 1}`,
      title: `补充页面 ${index + 1}`,
      intent: '补充说明前面结构中尚未覆盖的内容',
      user_notes: null,
    }
  ))
}

export async function generateSkeleton(taskId: string): Promise<Task> {
  await sleep(600)

  if (!currentTask || currentTask.task_id !== taskId) {
    throw new Error('任务不存在')
  }

  pollCount = 0
  currentTask = {
    ...currentTask,
    status: 'generating',
    updated_at: new Date().toISOString(),
    progress: {
      phase: 'skeleton_llm',
      current: null,
      total: null,
      message: '正在生成可编辑骨架。',
      percent: null,
    },
  }

  return currentTask
}

export async function updateSkeleton(
  taskId: string,
  slides: OutlineSkeletonSlide[],
  chapters?: Chapter[],
): Promise<Task> {
  await sleep(600)

  if (!currentTask || currentTask.task_id !== taskId) {
    throw new Error('任务不存在')
  }

  currentTask = {
    ...currentTask,
    outline_skeleton: slides,
    outline_skeleton_chapters: chapters ?? currentTask.outline_skeleton_chapters,
    updated_at: new Date().toISOString(),
    progress: {
      phase: 'skeleton_ready',
      current: null,
      total: slides.length,
      message: '骨架已更新，请确认后生成完整大纲。',
      percent: null,
    },
  }

  return currentTask
}

export async function saveOutline(
  taskId: string,
  outline: Outline,
): Promise<Task> {
  await sleep(600)

  if (!currentTask || currentTask.task_id !== taskId) {
    throw new Error('任务不存在')
  }

  currentTask = {
    ...currentTask,
    outline,
    updated_at: new Date().toISOString(),
  }

  return currentTask
}

export async function generateSlides(
  taskId: string,
  options?: GenerateSlidesRequest,
): Promise<Task> {
  await sleep(600)

  if (!currentTask || currentTask.task_id !== taskId) {
    throw new Error('任务不存在')
  }

  const total = currentTask.outline_skeleton?.length ?? 0

  pollCount = 0
  currentTask = {
    ...currentTask,
    status: 'generating',
    error: null,
    updated_at: new Date().toISOString(),
    runtime: {
      ...(currentTask.runtime ?? {}),
      retrieval_policy: {
        retrieval_depth: options?.retrieval_policy?.retrieval_depth ?? options?.retrieval_depth ?? 'L1',
        tavily_enabled: options?.retrieval_policy?.tavily_enabled ?? options?.tavily_enabled ?? true,
        prefer_user_doc: options?.retrieval_policy?.prefer_user_doc ?? false,
        source_quality: options?.retrieval_policy?.source_quality ?? 'medium',
        force_refresh: options?.retrieval_policy?.force_refresh ?? options?.force_refresh ?? false,
        enable_fallback_deepen: options?.retrieval_policy?.enable_fallback_deepen ?? false,
      },
    },
    outline: {
      title: currentTask.outline?.title ?? 'Mock PPT Outline',
      slides: [],
      evidence_catalog: [],
      page_evidence_map: [],
      meta: {
        retrieval_depth: 'L1',
        generated_at: new Date().toISOString(),
        schema_version: 'v1.0.0',
        partial: true,
        completed_pages: 0,
        failed_pages: 0,
        total_pages: total,
      },
    },
    progress: {
      phase: 'retrieving_page',
      current: 0,
      total,
      message: options?.force_refresh
        ? '正在强制刷新检索并生成…'
        : '正在准备按页生成。',
      percent: 0,
      slide_id: null,
      completed: 0,
      failed: 0,
    },
  }

  return currentTask!
}

export async function regenerateSlide(
  taskId: string,
  slideId: string,
  request?: RegenerateSlideRequest,
): Promise<RegenerateSlideResponse> {
  await sleep(400)

  if (!currentTask || currentTask.task_id !== taskId) {
    throw new Error('任务不存在')
  }

  pollCount = 0
  currentTask = {
    ...currentTask,
    status: 'generating',
    updated_at: new Date().toISOString(),
    progress: {
      phase: 'regenerating_slide',
      current: 1,
      total: 1,
      message: `正在重新生成 ${slideId}...`,
      percent: 0,
    },
  }

  console.log('Mock regenerate slide:', slideId, request?.user_instruction)

  return {
    task_id: taskId,
    status: 'generating',
    accepted: true,
    slide_id: slideId,
  }
}
