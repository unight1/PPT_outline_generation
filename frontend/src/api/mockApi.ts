import type {
  CreateTaskRequest,
  CreateTaskResponse,
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
    status: 'pending',
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

    if (pollCount >= 3) {
      currentTask = {
        ...mockTaskDone,
        task_id: taskId,
        created_at: currentTask.created_at,
        updated_at: new Date().toISOString(),
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