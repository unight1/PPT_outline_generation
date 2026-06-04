<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import type {
  CreateTaskRequest,
  GenerateSlidesRequest,
  OutlineSkeletonSlide,
  RetrievalDepth,
  Task,
} from './types/task'
import {
  createTask,
  generateSkeleton,
  generateSlides,
  getTask,
  regenerateSlide,
  submitClarification,
  updateSkeleton,
  saveOutline,
  apiModeLabel,
} from './api'
import { outlineToMarkdown } from './utils/outlineToMarkdown'
import SlideDeckView from './components/SlideDeckView.vue'
import GeneratingView from './components/GeneratingView.vue'
import TaskSidebar from './components/TaskSidebar.vue'

type ViewName = 'form' | 'status' | 'skeleton' | 'result'

const view = ref<ViewName>('form')
const loading = ref(false)
const errorMessage = ref('')
const task = ref<Task | null>(null)
const skeletonSlides = ref<OutlineSkeletonSlide[]>([])
const outlineDraft = ref<Task['outline'] | null>(null)
const savingOutline = ref(false)
const saveMessage = ref('')
const regeneratingSlideId = ref<string | null>(null)

const incrementalSlides = computed(() => {
  const currentTask = task.value
  if (!currentTask) return []

  const skeleton = currentTask.outline_skeleton ?? []
  const generatedSlides = currentTask.outline?.slides ?? []
  const generatedById = new Map(
    generatedSlides.map((slide) => [slide.slide_id, slide]),
  )

  if (skeleton.length > 0) {
    return skeleton.map((slide, index) => {
      const generated = generatedById.get(slide.slide_id)

      return {
        slide_id: slide.slide_id,
        title: generated?.title ?? slide.title,
        index,
        slide: generated ?? null,
        status: (generated ? 'done' : 'generating') as 'done' | 'generating' | 'failed',
      }
    })
  }

  return generatedSlides.map((slide, index) => ({
    slide_id: slide.slide_id,
    title: slide.title,
    index,
    slide,
    status: 'done' as const,
  }))
})

const showIncrementalOutline = computed(() => {
  if (!task.value) return false
  if (task.value.status !== 'generating') return false

  return (
    incrementalSlides.value.length > 0 ||
    Boolean(task.value.outline?.meta?.partial)
  )
})

const slideGenOptions = reactive<GenerateSlidesRequest>({
  retrieval_depth: 'L1',
  tavily_enabled: true,
  concurrency: 2,
  force_refresh: false,
})

const ERROR_CODE_LABELS: Record<string, string> = {
  LLM_ERROR: '模型生成失败',
  RETRIEVAL_ERROR: '本地检索失败',
  TAVILY_ERROR: '联网检索失败',
  TIMEOUT: '处理超时',
  INTERNAL_ERROR: '服务内部错误',
  GENERATION_TIMEOUT: '生成超时',
  RETRIEVAL_UNAVAILABLE: '检索服务不可用',
}

const form = reactive<CreateTaskRequest>({
  topic: '',
  source_type: 'short_topic',
  audience: '',
  duration_minutes: 15,
  language: 'zh',
  retrieval_depth: 'L1',
  raw_notes: '',
  document_title: '',
  document_text: '',
})

const answers = reactive<Record<string, string>>({})

const statusText = computed(() => {
  const status = task.value?.status

  if (status === 'pending') return '已创建，等待生成'
  if (status === 'clarifying') return '正在收集需求澄清'
  if (status === 'generating') return '正在生成大纲'
  if (status === 'done') return '生成完成'
  if (status === 'failed') return '生成失败'

  return '尚未创建任务'
})

const progressText = computed(() => {
  const progress = task.value?.progress
  if (!progress) return ''
  return progress.message || '处理中'
})

const taskErrorLabel = computed(() => {
  const code = task.value?.error?.code
  if (!code) return '未知错误'
  return ERROR_CODE_LABELS[code] ?? code
})

const taskErrorDetailLines = computed(() => {
  const details = task.value?.error?.details
  if (!details) return []
  const lines: string[] = []
  if (typeof details.phase === 'string') {
    lines.push(`阶段：${details.phase}`)
  }
  if (typeof details.slide_id === 'string') {
    lines.push(`相关页面：${details.slide_id}`)
  }
  if (typeof details.reason === 'string') {
    lines.push(`原因：${details.reason}`)
  }
  if (details.retryable === false) {
    lines.push('该错误暂不支持自动重试')
  }
  return lines
})

const canRetrySlideGeneration = computed(() => {
  if (!task.value || task.value.status !== 'failed') return false
  if (!skeletonSlides.value.length) return false
  const retryable = task.value.error?.details?.retryable
  return retryable !== false
})

function syncSkeletonFromTask() {
  skeletonSlides.value = (task.value?.outline_skeleton ?? []).map((slide) => ({
    ...slide,
    intent: slide.intent ?? '',
    user_notes: slide.user_notes ?? '',
  }))
}

function enterSkeletonView() {
  syncSkeletonFromTask()
  slideGenOptions.retrieval_depth = (form.retrieval_depth ?? 'L1') as RetrievalDepth
  view.value = 'skeleton'
}

function buildSlideGeneratePayload(): GenerateSlidesRequest {
  return {
    concurrency: slideGenOptions.concurrency,
    force_refresh: slideGenOptions.force_refresh,
    retrieval_depth: slideGenOptions.retrieval_depth,
    tavily_enabled: slideGenOptions.tavily_enabled,
  }
}

async function runSlideGenerationFlow() {
  if (!task.value) return
  if (!skeletonSlides.value.length) {
    errorMessage.value = '请先生成并确认骨架'
    return
  }

  loading.value = true
  errorMessage.value = ''

  try {
    task.value = await updateSkeleton(task.value.task_id, skeletonSlides.value)
    task.value = await generateSlides(task.value.task_id, buildSlideGeneratePayload())
    await pollTaskUntilSettled({
      done: (latestTask) => latestTask.status === 'done',
      onDone: (latestTask) => {
        if (latestTask.status === 'done') {
          outlineDraft.value = cloneOutline(latestTask.outline)
          saveMessage.value = ''
          view.value = 'result'
        }
      },
      timeoutMessage: '按页生成轮询超时',
    })
  } catch (error) {
    loading.value = false
    errorMessage.value = error instanceof Error ? error.message : '按页生成失败'
  }
}

function validateForm() {
  if (!form.topic.trim()) {
    errorMessage.value = '请先填写 PPT 主题'
    return false
  }

  if (
    form.duration_minutes !== undefined &&
    (form.duration_minutes < 5 || form.duration_minutes > 120)
  ) {
    errorMessage.value = '演示时长建议在 5 到 120 分钟之间'
    return false
  }

  if (form.source_type === 'long_document' && !(form.document_text ?? '').trim()) {
    errorMessage.value = '选择"长文档"时，需填写文档正文'
    return false
  }

  return true
}

async function handleCreateTask() {
  if (!validateForm()) return

  loading.value = true
  errorMessage.value = ''

  try {
    const result = await createTask(form)
    task.value = await getTask(result.task_id)

    task.value.clarification?.questions.forEach((question) => {
      answers[question.question_id] = question.answer ?? ''
    })

    view.value = 'status'
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '创建任务失败'
  } finally {
    loading.value = false
  }
}

async function handleSubmitClarification() {
  if (!task.value) return

  loading.value = true
  errorMessage.value = ''

  try {
    task.value = await submitClarification(task.value.task_id, answers)
    syncSkeletonFromTask()
    view.value = 'skeleton'
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '提交澄清失败'
  } finally {
    loading.value = false
  }
}

async function pollTaskUntilSettled(
  options: {
    done: (latestTask: Task) => boolean
    onDone?: (latestTask: Task) => void
    timeoutMessage: string
  },
) {
  if (!task.value) return
  const taskId = task.value.task_id
  const pollStart = Date.now()
  const maxPollMs = 15 * 60 * 1000
  let pollingInFlight = false

  const timer = window.setInterval(() => {
    if (pollingInFlight) return

    void (async () => {
      pollingInFlight = true
      try {
        const latestTask = await getTask(taskId)
        task.value = latestTask
        syncSkeletonFromTask()

        if (latestTask.status === 'failed' || options.done(latestTask)) {
          window.clearInterval(timer)
          loading.value = false
          options.onDone?.(latestTask)
        } else if (Date.now() - pollStart > maxPollMs) {
          window.clearInterval(timer)
          loading.value = false
          errorMessage.value = `${options.timeoutMessage}（当前状态：${latestTask.status}），请稍后刷新任务状态。`
        }
      } catch (error) {
        window.clearInterval(timer)
        loading.value = false
        errorMessage.value = error instanceof Error ? error.message : '轮询任务状态失败'
      } finally {
        pollingInFlight = false
      }
    })()
  }, 1200)
}

function cloneOutline(outline: Task['outline']) {
  return outline ? JSON.parse(JSON.stringify(outline)) : null
}

async function handleSaveOutline() {
  if (!task.value || !outlineDraft.value) return

  savingOutline.value = true
  saveMessage.value = ''
  errorMessage.value = ''

  try {
    task.value = await saveOutline(task.value.task_id, outlineDraft.value)
    outlineDraft.value = cloneOutline(task.value.outline)
    saveMessage.value = '修改已保存。'
  } catch (error) {
    errorMessage.value =
      error instanceof Error ? error.message : '保存大纲失败，请稍后重试。'
  } finally {
    savingOutline.value = false
  }
}

async function handleGenerateSkeleton() {
  if (!task.value) return

  if (task.value.clarification && !task.value.clarification.submitted) {
    errorMessage.value = '请先提交需求澄清，再生成骨架。'
    return
  }

  loading.value = true
  errorMessage.value = ''

  try {
    task.value = await generateSkeleton(task.value.task_id)
    await pollTaskUntilSettled({
      done: (latestTask) => latestTask.status === 'pending' && Boolean(latestTask.outline_skeleton?.length),
      timeoutMessage: '骨架生成轮询超时',
    })
  } catch (error) {
    loading.value = false
    errorMessage.value = error instanceof Error ? error.message : '骨架生成失败'
  }
}

async function handleSaveSkeleton() {
  if (!task.value) return
  if (!skeletonSlides.value.length) {
    errorMessage.value = '请先生成骨架'
    return
  }

  loading.value = true
  errorMessage.value = ''

  try {
    task.value = await updateSkeleton(task.value.task_id, skeletonSlides.value)
    syncSkeletonFromTask()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '保存骨架失败'
  } finally {
    loading.value = false
  }
}

async function handleGenerateSlides() {
  await runSlideGenerationFlow()
}

async function handleRetrySlideGeneration() {
  await runSlideGenerationFlow()
}

function addSkeletonSlide() {
  const next = skeletonSlides.value.length + 1
  skeletonSlides.value.push({
    slide_id: `s${next}`,
    title: `新增页面 ${next}`,
    intent: '',
    user_notes: '',
  })
}

function removeSkeletonSlide(index: number) {
  skeletonSlides.value.splice(index, 1)
}

async function handleRegenerateSlide(slideId: string, userInstruction?: string) {
  if (!task.value || regeneratingSlideId.value) return
  regeneratingSlideId.value = slideId
  errorMessage.value = ''

  try {
    await regenerateSlide(task.value.task_id, slideId, {
      user_instruction: userInstruction || undefined,
    })
    task.value = await getTask(task.value.task_id)

    const pollStart = Date.now()
    const maxPollMs = 10 * 60 * 1000
    let pollingInFlight = false

    const timer = window.setInterval(() => {
      if (!task.value) return
      if (pollingInFlight) return

      void (async () => {
        pollingInFlight = true
        try {
          const latestTask = await getTask(task.value!.task_id)
          task.value = latestTask

          if (latestTask.status === 'done' || latestTask.status === 'failed') {
            window.clearInterval(timer)
            regeneratingSlideId.value = null
            outlineDraft.value = cloneOutline(latestTask.outline)
            if (latestTask.status === 'done') {
              saveMessage.value = '该页已重新生成。'
            }
          } else if (Date.now() - pollStart > maxPollMs) {
            window.clearInterval(timer)
            regeneratingSlideId.value = null
            errorMessage.value = '单页重生成轮询超时'
          }
        } catch (error) {
          window.clearInterval(timer)
          regeneratingSlideId.value = null
          errorMessage.value = error instanceof Error ? error.message : '重生成失败'
        } finally {
          pollingInFlight = false
        }
      })()
    }, 1200)
  } catch (error) {
    regeneratingSlideId.value = null
    errorMessage.value = error instanceof Error ? error.message : '重生成失败'
  }
}

function restart() {
  view.value = 'form'
  task.value = null
  outlineDraft.value = null
  savingOutline.value = false
  saveMessage.value = ''
  regeneratingSlideId.value = null
  errorMessage.value = ''
  form.topic = ''
  form.source_type = 'short_topic'
  form.audience = ''
  form.duration_minutes = 15
  form.language = 'zh'
  form.retrieval_depth = 'L1'
  form.raw_notes = ''
  form.document_title = ''
  form.document_text = ''
  skeletonSlides.value = []
}

const copyMessage = ref('')

function handleCopyMarkdown() {
  const outlineVal = outlineDraft.value
  if (!outlineVal) return
  try {
    const md = outlineToMarkdown(outlineVal)
    navigator.clipboard.writeText(md).then(() => {
      copyMessage.value = '已复制到剪贴板'
      setTimeout(() => (copyMessage.value = ''), 2000)
    })
  } catch {
    errorMessage.value = '复制 Markdown 失败'
  }
}

function handleDownloadMarkdown() {
  const outlineVal = outlineDraft.value
  if (!outlineVal) return
  const md = outlineToMarkdown(outlineVal)
  const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${outlineVal.title || 'outline'}.md`
  a.click()
  URL.revokeObjectURL(url)
}

function handleUpdateSlide(updatedSlide: typeof outlineDraft.value extends { slides: (infer S)[] } | null ? S : never) {
  if (!outlineDraft.value) return
  outlineDraft.value = {
    ...outlineDraft.value,
    slides: outlineDraft.value.slides.map((s) =>
      (s as { slide_id: string }).slide_id === (updatedSlide as { slide_id: string }).slide_id
        ? { ...s, ...updatedSlide }
        : s,
    ),
  }
}
</script>

<template>
  <main class="page">
    <section class="hero">
      <p class="eyebrow">PPT Outline Generation</p>
      <h1>智能 PPT 大纲生成前端 Demo</h1>
      <p class="subtitle">
       当前接口模式：{{ apiModeLabel }}。
      </p>
    </section>

    <section class="steps">
      <div :class="['step', view === 'form' && 'active']">1. 基本信息</div>
      <div :class="['step', view === 'status' && 'active']">2. 回答问题</div>
      <div :class="['step', view === 'skeleton' && 'active']">3. 确认骨架</div>
      <div :class="['step', view === 'result' && 'active']">4. 查看大纲</div>
    </section>

    <p v-if="errorMessage" class="error">{{ errorMessage }}</p>

    <section v-if="view === 'form'" class="card">
      <h2>需求澄清表单</h2>

      <label>
        PPT 主题 <span class="required">*</span>
        <input v-model="form.topic" placeholder="例如：基于 RAG 的 PPT 大纲智能生成系统" />
      </label>

      <label>
        输入类型
        <select v-model="form.source_type">
          <option value="short_topic">短主题</option>
          <option value="long_document">长文档</option>
        </select>
      </label>

      <label>
        听众 / 场景
        <input v-model="form.audience" placeholder="例如：课程答辩、产品汇报、本科生课堂展示" />
      </label>

      <label>
        演示时长，分钟
        <input v-model.number="form.duration_minutes" type="number" min="5" max="120" />
      </label>

      <label>
        检索深度
        <select v-model="form.retrieval_depth">
          <option value="L0">L0：轻量</option>
          <option value="L1">L1：默认平衡</option>
          <option value="L2">L2：深度</option>
        </select>
      </label>

      <label>
        补充材料
        <textarea
          v-model="form.raw_notes"
          placeholder="可以粘贴老师要求、参考资料、你已有的想法"
        />
      </label>

      <template v-if="form.source_type === 'long_document'">
        <label>
          文档标题（可选）
          <input v-model="form.document_title" placeholder="例如：RAG 在教学场景中的应用研究" />
        </label>

        <label>
          文档正文 <span class="required">*</span>
          <textarea
            v-model="form.document_text"
            placeholder="请粘贴长文档正文，后端将用于提炼重点与生成大纲"
          />
        </label>
      </template>

      <button :disabled="loading" @click="handleCreateTask">
        {{ loading ? '创建中...' : '创建任务' }}
      </button>
    </section>

    <section v-if="view === 'status' && task" class="card">
      <h2>任务状态</h2>

      <div class="status-box">
        <strong>{{ statusText }}</strong>
        <span>任务 ID：{{ task.task_id }}</span>
      </div>

      <div v-if="task.clarification" class="clarification">
        <h3>需求澄清问题</h3>

        <label
          v-for="question in task.clarification.questions"
          :key="question.question_id"
        >
          {{ question.prompt }}
          <textarea v-model="answers[question.question_id]" />
        </label>

        <button :disabled="loading" @click="handleSubmitClarification">
          {{ loading ? '提交中...' : '提交澄清，进入骨架确认' }}
        </button>
      </div>

      <div v-if="task.clarification?.submitted" class="actions">
        <button :disabled="loading" @click="enterSkeletonView">继续：骨架确认</button>
        <button class="secondary" @click="restart">重新开始</button>
      </div>
      <div v-else class="actions">
        <button class="secondary" @click="restart">重新开始</button>
      </div>

      <div v-if="task.status === 'generating'" class="progress-box">
        <strong>
          {{ task.progress?.message || '处理中，请稍候…' }}
        </strong>
        <p class="hint">
          当前阶段：{{ task.progress?.phase || 'processing' }}
          <span v-if="task.progress?.current != null && task.progress?.total != null">
            ｜第 {{ task.progress.current }} / {{ task.progress.total }} 页
          </span>
        </p>
        <div
          v-if="typeof task.progress?.percent === 'number'"
          class="progress-track"
        >
          <div
            class="progress-fill"
            :style="{ width: `${task.progress.percent}%` }"
          />
        </div>
        <p v-if="typeof task.progress?.percent === 'number'" class="hint">
          进度：{{ task.progress.percent }}%
        </p>
      </div>

      <div v-if="task.status === 'failed'" class="failed-box">
        <strong>任务失败：{{ taskErrorLabel }}</strong>
        <p>错误码：{{ task.error?.code ?? 'UNKNOWN' }}</p>
        <p>{{ task.error?.message ?? '后端未返回错误信息' }}</p>
        <p v-for="(line, idx) in taskErrorDetailLines" :key="idx" class="hint">{{ line }}</p>
      </div>
    </section>

    <section v-if="view === 'skeleton' && task" class="card">
      <h2>骨架确认</h2>

      <div class="status-box">
        <strong>{{ statusText }}</strong>
        <span>任务 ID：{{ task.task_id }}</span>
      </div>

      <p v-if="progressText" class="hint">{{ progressText }}</p>
      <div v-if="task.progress?.percent !== null && task.progress?.percent !== undefined" class="progress-bar">
        <div class="progress-fill" :style="{ width: `${task.progress.percent}%` }" />
      </div>

      <div v-if="!skeletonSlides.length" class="empty-box">
        <p>提交澄清后先生成 PPT 页级骨架，确认每页主题后再按页生成完整内容。</p>
        <button :disabled="loading || task.status === 'generating'" @click="handleGenerateSkeleton">
          {{ task.status === 'generating' ? '骨架生成中...' : '生成骨架' }}
        </button>
      </div>

      <div v-else class="skeleton-list">
        <article
          v-for="(slide, index) in skeletonSlides"
          :key="slide.slide_id"
          class="skeleton-slide"
        >
          <div class="skeleton-heading">
            <strong>第 {{ index + 1 }} 页 / {{ slide.slide_id }}</strong>
            <button class="secondary danger" type="button" @click="removeSkeletonSlide(index)">
              删除
            </button>
          </div>

          <label>
            页面标题
            <input v-model="slide.title" />
          </label>

          <label>
            页面意图
            <textarea v-model="slide.intent" />
          </label>

          <label>
            补充要求
            <textarea v-model="slide.user_notes" placeholder="可写给后续按页生成的额外要求" />
          </label>
        </article>

        <div class="gen-options">
          <h3>按页生成参数</h3>
          <label>
            检索深度
            <select v-model="slideGenOptions.retrieval_depth">
              <option value="L0">L0：仅本地 / 轻量</option>
              <option value="L1">L1：默认平衡</option>
              <option value="L2">L2：深度检索</option>
            </select>
          </label>
          <label class="checkbox-row">
            <input v-model="slideGenOptions.tavily_enabled" type="checkbox" />
            启用联网检索（Tavily）
          </label>
          <label>
            按页并发数
            <select v-model.number="slideGenOptions.concurrency">
              <option :value="1">1（最稳）</option>
              <option :value="2">2（推荐）</option>
              <option :value="3">3（最快）</option>
            </select>
          </label>
          <label class="checkbox-row">
            <input v-model="slideGenOptions.force_refresh" type="checkbox" />
            强制刷新检索缓存（骨架未改但想重新搜资料时勾选）
          </label>
        </div>

        <div class="actions">
          <button class="secondary" type="button" @click="addSkeletonSlide">新增页面</button>
          <button :disabled="loading" type="button" @click="handleSaveSkeleton">
            {{ loading ? '保存中...' : '保存骨架' }}
          </button>
          <button
            :disabled="loading || task.status === 'generating'"
            type="button"
            @click="handleGenerateSlides"
          >
            {{ task.status === 'generating' ? '生成中...' : '按页生成完整大纲' }}
          </button>
        </div>
      </div>

      <div v-if="task.status === 'failed'" class="failed-box">
        <strong>任务失败：{{ taskErrorLabel }}</strong>
        <p>错误码：{{ task.error?.code ?? 'UNKNOWN' }}</p>
        <p>{{ task.error?.message ?? '后端未返回错误信息' }}</p>
        <p v-for="(line, idx) in taskErrorDetailLines" :key="`sk-${idx}`" class="hint">{{ line }}</p>
        <button
          v-if="canRetrySlideGeneration"
          :disabled="loading || !skeletonSlides.length"
          type="button"
          @click="handleRetrySlideGeneration"
        >
          {{ loading ? '重试中...' : '重试按页生成' }}
        </button>
      </div>
    </section>

    <!-- A4: 结果页 · 一页一屏翻页工作台 -->
    <section v-if="view === 'result' && outlineDraft" class="card">
      <div class="result-header">
        <div>
          <p class="eyebrow">Outline Result</p>
          <h2>完整大纲结果</h2>
          <p v-if="task?.outline">
            检索深度：{{ task.outline.meta.retrieval_depth ?? '未返回' }} · 生成时间：
            {{ task.outline.meta.generated_at ?? '未返回' }}
          </p>
        </div>

        <div class="actions">
          <button
            class="primary"
            :disabled="savingOutline"
            @click="handleSaveOutline"
          >
            {{ savingOutline ? '保存中…' : '保存修改' }}
          </button>
          <button class="secondary" @click="restart">生成新的大纲</button>
          <button class="secondary" @click="handleCopyMarkdown">复制 Markdown</button>
          <button class="secondary" @click="handleDownloadMarkdown">下载 .md</button>
        </div>
      </div>

      <p v-if="copyMessage" class="success-message">{{ copyMessage }}</p>
      <p v-if="saveMessage" class="success-message">{{ saveMessage }}</p>

      <label class="field">
        整稿标题
        <input v-model="outlineDraft.title" />
      </label>

      <div class="result-body">
        <SlideDeckView
          :outline="outlineDraft"
          :task-progress="task?.progress ?? null"
          :regenerating-slide-id="regeneratingSlideId"
          :saving="savingOutline"
          :save-message="saveMessage"
          @save="handleSaveOutline"
          @restart="restart"
          @regenerate="handleRegenerateSlide"
          @copy-markdown="handleCopyMarkdown"
          @download-markdown="handleDownloadMarkdown"
          @update:slide="handleUpdateSlide"
        />

        <TaskSidebar show-history />
      </div>

    </section>
  </main>

    <!-- Generating progress dialog -->
    <GeneratingView
      v-if="showIncrementalOutline && task"
      :task="task"
      :slides="incrementalSlides"
      @close="() => {}"
    />
  </template>

<style scoped>
.page {
  max-width: 960px;
  margin: 0 auto;
  padding: 40px 20px;
  font-family:
    Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  color: #172033;
}

.hero {
  margin-bottom: 24px;
}

.eyebrow {
  margin: 0 0 8px;
  color: #5d6b82;
  font-size: 14px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

h1 {
  margin: 0;
  font-size: 36px;
}

.subtitle {
  color: #5d6b82;
  line-height: 1.7;
}

.steps {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-bottom: 20px;
}

.step {
  padding: 12px;
  border: 1px solid #d9e0ea;
  border-radius: 12px;
  background: #f7f9fc;
  text-align: center;
  color: #5d6b82;
}

.step.active {
  border-color: #2864d8;
  background: #eaf1ff;
  color: #1f4eb0;
  font-weight: 700;
}

.card {
  padding: 24px;
  border: 1px solid #d9e0ea;
  border-radius: 18px;
  background: #ffffff;
  box-shadow: 0 12px 40px rgba(20, 33, 61, 0.08);
}

label {
  display: block;
  margin: 16px 0;
  font-weight: 700;
}

input,
select,
textarea {
  box-sizing: border-box;
  width: 100%;
  margin-top: 8px;
  padding: 12px;
  border: 1px solid #cbd5e1;
  border-radius: 10px;
  font: inherit;
}

textarea {
  min-height: 90px;
  resize: vertical;
}

button {
  padding: 12px 18px;
  border: none;
  border-radius: 10px;
  background: #2864d8;
  color: white;
  font-weight: 700;
  cursor: pointer;
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

button.secondary {
  background: #eef2f7;
  color: #172033;
}

button.danger {
  color: #991b1b;
}

.required,
.error {
  color: #d72d2d;
}

.status-box {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 16px;
  border-radius: 12px;
  background: #f7f9fc;
}

.actions,
.result-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  margin-top: 20px;
  flex-wrap: wrap;
}

.actions button,
.result-header button {
  white-space: nowrap;
  flex-shrink: 0;
}

.hint {
  color: #5d6b82;
}

/* C2: 字段说明副标题 */
.field-hint {
  display: inline;
  margin-left: 8px;
  font-size: 12px;
  font-weight: 400;
  color: #5d6b82;
}

.progress-bar {
  overflow: hidden;
  height: 8px;
  margin-top: 12px;
  border-radius: 999px;
  background: #e5eaf3;
}

.progress-fill {
  height: 100%;
  border-radius: inherit;
  background: #2864d8;
  transition: width 0.2s ease;
}

.empty-box,
.skeleton-slide {
  margin-top: 16px;
  padding: 18px;
  border: 1px solid #e3e8f0;
  border-radius: 14px;
  background: #fbfcff;
}

.skeleton-heading {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.slide-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.slide-header h3 {
  margin: 0;
  flex: 1;
}

button.small {
  padding: 6px 12px;
  font-size: 13px;
  white-space: nowrap;
}

.result-body {
  display: grid;
  grid-template-columns: 1fr 240px;
  gap: 24px;
  align-items: start;
  margin-top: 16px;
}

@media (max-width: 900px) {
  .result-body {
    grid-template-columns: 1fr;
  }
}

.slide {
  margin-top: 16px;
  padding: 18px;
  border: 1px solid #e3e8f0;
  border-radius: 14px;
  background: #fbfcff;
}

.slide li {
  margin: 10px 0;
  line-height: 1.6;
}

.evidence-tag {
  display: inline-block;
  margin-left: 8px;
  padding: 3px 8px;
  border-radius: 999px;
  background: #eaf1ff;
  color: #1f4eb0;
  font-size: 12px;
}

.notes {
  color: #5d6b82;
}

.gen-options {
  display: grid;
  gap: 0.75rem;
  margin: 1rem 0;
  padding: 1rem;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
}

.gen-options h3 {
  margin: 0;
  font-size: 1rem;
}

.checkbox-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.failed-box {
  margin-top: 16px;
  padding: 16px;
  border-radius: 12px;
  background: #fff5f5;
  border: 1px solid #fecaca;
  color: #991b1b;
}

.failed-box p {
  margin: 8px 0 0;
}

@media (max-width: 720px) {
  .steps {
    grid-template-columns: repeat(2, 1fr);
  }

  .status-box,
  .actions,
  .result-header {
    grid-template-columns: 1fr;
    display: block;
  }

  .step,
  button {
    width: 100%;
    margin-top: 8px;
  }
}

.success-message {
  padding: 10px 12px;
  margin: 12px 0;
  border-radius: 10px;
  background: #ecfdf5;
  color: #047857;
}

.progress-box {
  margin-top: 16px;
  padding: 16px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}

.progress-track {
  width: 100%;
  height: 10px;
  margin-top: 12px;
  border-radius: 999px;
  background: #e5e7eb;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: 999px;
  background: #2563eb;
  transition: width 0.3s ease;
}

.evidence-section {
  margin-top: 24px;
}

</style>
