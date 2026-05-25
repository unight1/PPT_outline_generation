import type {
  CreateTaskRequest,
  CreateTaskResponse,
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

export async function createTask(
  request: CreateTaskRequest,
): Promise<CreateTaskResponse> {
  await sleep(600)

  currentTask = {
    ...mockTaskClarifying,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
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
    } else if (currentTask.progress?.phase !== 'skeleton_llm' && pollCount >= 3) {
      currentTask = {
        ...mockTaskDone,
        task_id: taskId,
        created_at: currentTask.created_at,
        updated_at: new Date().toISOString(),
        outline_skeleton: currentTask.outline_skeleton ?? mockTaskDone.outline_skeleton,
      }
    }
  }

  return currentTask
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
  return [
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
): Promise<Task> {
  await sleep(600)

  if (!currentTask || currentTask.task_id !== taskId) {
    throw new Error('任务不存在')
  }

  currentTask = {
    ...currentTask,
    outline_skeleton: slides,
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

export async function generateSlides(taskId: string): Promise<Task> {
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
      phase: 'retrieving_page',
      current: 0,
      total: currentTask.outline_skeleton?.length ?? null,
      message: '正在准备按页生成。',
      percent: 0,
    },
  }

  return currentTask
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
