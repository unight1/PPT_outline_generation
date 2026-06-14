<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  NButton,
  NCard,
  NCheckbox,
  NConfigProvider,
  NGi,
  NGrid,
  NInput,
  NInputNumber,
  NMessageProvider,
  NModal,
  NSelect,
  NSpace,
  NSteps,
  NStep,
  NTag,
  NText,
  NCollapse,
  NCollapseItem,
} from 'naive-ui'
import type {
  Chapter,
  CreateTaskRequest,
  GenerateSlidesRequest,
  OutlineSkeletonSlide,
  RetrievalPolicy,
  RetrievalDepth,
  SourceQuality,
  Task,
  TaskListItem,
} from './types/task'
import {
  createTask,
  generateSkeleton,
  generateSlides,
  getTask,
  listTasks,
  regenerateSlide,
  submitClarification,
  updateSkeleton,
  uploadTaskDocument,
  saveOutline,
  apiModeLabel,
} from './api'
import { outlineToMarkdown } from './utils/outlineToMarkdown'
import SlideDeckView from './components/SlideDeckView.vue'
import GeneratingView from './components/GeneratingView.vue'
import TaskSidebar from './components/TaskSidebar.vue'
import LoginView from './components/LoginView.vue'
import EvalView from './components/EvalView.vue'

type ViewName = 'form' | 'status' | 'skeleton' | 'result'
type AppPage = 'workflow' | 'eval'
const currentPage = ref<AppPage>('workflow')
type SlideGenForm = Omit<GenerateSlidesRequest, 'retrieval_policy'> & {
  retrieval_policy: RetrievalPolicy
}

const view = ref<ViewName>('form')
const loggedIn = ref(false)
const currentUsername = ref('')
const loading = ref(false)
const errorMessage = ref('')
const task = ref<Task | null>(null)
const skeletonSlides = ref<OutlineSkeletonSlide[]>([])
const skeletonChapters = ref<Chapter[]>([])
const outlineDraft = ref<Task['outline'] | null>(null)
const savingOutline = ref(false)
const saveMessage = ref('')
const regeneratingSlideId = ref<string | null>(null)
const taskHistory = ref<TaskListItem[]>([])
const historyLoading = ref(false)
const uploadingDocument = ref(false)
const longDocumentFileName = ref('')
const readingLongDocument = ref(false)
const DOCUMENT_UPLOAD_MAX_BYTES = 2_000_000

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
      const status = generated?.generation_status === 'failed'
        ? 'failed'
        : generated
          ? 'done'
          : 'generating'

      return {
        slide_id: slide.slide_id,
        title: generated?.title ?? slide.title,
        index,
        slide: generated ?? null,
        status: status as 'done' | 'generating' | 'failed',
      }
    })
  }

  return generatedSlides.map((slide, index) => ({
    slide_id: slide.slide_id,
    title: slide.title,
    index,
    slide,
    status: (slide.generation_status === 'failed' ? 'failed' : 'done') as 'done' | 'failed',
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

const slideGenOptions = reactive<SlideGenForm>({
  retrieval_depth: 'L1',
  tavily_enabled: true,
  concurrency: 2,
  force_refresh: false,
  retrieval_policy: {
    retrieval_depth: 'L1',
    tavily_enabled: true,
    prefer_user_doc: false,
    source_quality: 'medium',
    force_refresh: false,
    enable_fallback_deepen: false,
  },
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

const currentStep = computed(() => {
  if (view.value === 'form') return 1
  if (view.value === 'status') return 2
  if (view.value === 'skeleton') return 3
  if (view.value === 'result') return 4
  return 1
})

const footerHint = computed(() => {
  if (errorMessage.value) return errorMessage.value
  if (copyMessage.value) return copyMessage.value
  if (saveMessage.value) return saveMessage.value
  if (loading.value) return '处理中…'
  return ''
})

const form = reactive<CreateTaskRequest>({
  topic: '',
  source_type: 'short_topic',
  audience: '',
  duration_minutes: 15,
  target_pages_min: 8,
  target_pages_max: 12,
  desired_chapters: '',
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

const taskErrorLabel = computed(() => {
  const code = task.value?.error?.code
  if (!code) return '未知错误'
  return ERROR_CODE_LABELS[code] ?? code
})

const taskErrorDetails = computed(() => {
  const details = task.value?.error?.details
  if (!details) return []
  const rows: string[] = []
  if (typeof details.phase === 'string') rows.push(`失败阶段：${details.phase}`)
  if (typeof details.slide_id === 'string') rows.push(`相关页面：${details.slide_id}`)
  if (typeof details.retryable === 'boolean') rows.push(details.retryable ? '可以重试' : '不建议重试')
  if (typeof details.reason === 'string') rows.push(`原因：${details.reason}`)
  return rows
})

const isDocumentAnalyzing = computed(() => {
  if (task.value?.input?.source_type !== 'long_document') return false
  const analysisStatus = task.value?.runtime?.document_analysis_status
  return analysisStatus === 'running' || analysisStatus === 'pending'
})

const clarificationReady = computed(() => {
  const questions = task.value?.clarification?.questions
  if (!questions?.length) return false
  return !isDocumentAnalyzing.value
})

const documentAnalysisStatusLabel = computed(() => {
  const status = task.value?.runtime?.document_analysis_status
  if (status === 'running') return '分析中'
  if (status === 'pending') return '等待开始'
  if (status === 'failed') return '分析失败'
  return '已完成'
})

const documentAnalysisText = computed(() => {
  const progressMessage = task.value?.progress?.message?.trim()
  if (isDocumentAnalyzing.value) {
    return progressMessage || '正在阅读并提炼文档摘要，完成后会自动生成澄清问题，请稍候…'
  }
  const status = task.value?.runtime?.document_analysis_status
  if (status === 'failed') {
    return '智能摘要失败，已使用规则画像生成澄清问题，可继续作答。'
  }
  return ''
})

const skeletonChapterGroups = computed(() => {
  const titleBySlideId = new Map(skeletonSlides.value.map((slide) => [slide.slide_id, slide.title]))
  const readableTitle = (chapterId: string, title: string | undefined, slideIds: string[]) => {
    if (title && !/^ch\d+$/i.test(title)) return title
    const firstTitle = slideIds.map((slideId) => titleBySlideId.get(slideId)).find(Boolean)
    return firstTitle ? `章节：${firstTitle}` : chapterId
  }
  const chapters = skeletonChapters.value
  if (chapters.length) {
    return chapters.map((chapter) => ({
      ...chapter,
      title: readableTitle(chapter.chapter_id, chapter.title, chapter.slide_ids),
    }))
  }
  const grouped = new Map<string, string[]>()
  for (const slide of skeletonSlides.value) {
    const chapterId = String((slide as OutlineSkeletonSlide & { chapter_id?: string | null }).chapter_id || '')
    if (!chapterId) continue
    grouped.set(chapterId, [...(grouped.get(chapterId) ?? []), slide.slide_id])
  }
  return Array.from(grouped, ([chapter_id, slide_ids]) => ({
    chapter_id,
    title: readableTitle(chapter_id, chapter_id, slide_ids),
    slide_ids,
  }))
})

function syncSkeletonFromTask() {
  skeletonSlides.value = (task.value?.outline_skeleton ?? []).map((slide) => ({
    ...slide,
    intent: slide.intent ?? '',
    user_notes: slide.user_notes ?? '',
  }))
  skeletonChapters.value = normalizeSkeletonChapters(
    task.value?.outline_skeleton_chapters ?? [],
    skeletonSlides.value,
  )
}

function normalizeSkeletonChapters(
  chapters: Chapter[],
  slides: OutlineSkeletonSlide[],
): Chapter[] {
  const validIds = new Set(slides.map((slide) => slide.slide_id))
  const titleBySlideId = new Map(slides.map((slide) => [slide.slide_id, slide.title]))
  const desiredChapters = String(task.value?.input?.desired_chapters || form.desired_chapters || "")
    .split(/[,，;；、\n]+/)
    .map((item) => item.trim())
    .filter(Boolean)
  const cleaned = chapters
    .map((chapter, index) => ({
      chapter_id: chapter.chapter_id || `ch${index + 1}`,
      title:
        chapter.title && !/^ch\d+$/i.test(chapter.title)
          ? chapter.title
          : `章节：${titleBySlideId.get(chapter.slide_ids[0]) || index + 1}`,
      slide_ids: chapter.slide_ids.filter((slideId) => validIds.has(slideId)),
    }))
    .filter((chapter) => chapter.slide_ids.length > 0 || chapters.length <= 1)

  if (cleaned.length > 0) {
    const assigned = new Set(cleaned.flatMap((chapter) => chapter.slide_ids))
    for (const slide of slides) {
      if (!assigned.has(slide.slide_id)) {
        cleaned[0].slide_ids.push(slide.slide_id)
        slide.chapter_id = cleaned[0].chapter_id
      }
    }
    return cleaned
  }

  if (!slides.length) return []
  const chapterCount = Math.min(
    Math.max(desiredChapters.length || Math.ceil(slides.length / 3), 2),
    Math.min(5, slides.length),
  )
  const baseSize = Math.floor(slides.length / chapterCount)
  const remainder = slides.length % chapterCount
  let cursor = 0
  return Array.from({ length: chapterCount }, (_, index) => {
    const size = baseSize + (index < remainder ? 1 : 0)
    const groupSlides = slides.slice(cursor, cursor + size)
    cursor += size
    const chapterId = `ch${index + 1}`
    groupSlides.forEach((slide) => {
      slide.chapter_id = chapterId
    })
    return {
      chapter_id: chapterId,
      title: desiredChapters[index] || `章节：${groupSlides[0]?.title || index + 1}`,
      slide_ids: groupSlides.map((slide) => slide.slide_id),
    }
  })
}

function assignSlideToChapter(slideId: string, chapterId: string) {
  skeletonSlides.value = skeletonSlides.value.map((slide) =>
    slide.slide_id === slideId ? { ...slide, chapter_id: chapterId } : slide,
  )
  skeletonChapters.value = skeletonChapters.value.map((chapter) => ({
    ...chapter,
    slide_ids: chapter.chapter_id === chapterId
      ? Array.from(new Set([...chapter.slide_ids, slideId]))
      : chapter.slide_ids.filter((id) => id !== slideId),
  }))
}

function updateChapterTitle(chapterId: string, title: string) {
  skeletonChapters.value = skeletonChapters.value.map((chapter) =>
    chapter.chapter_id === chapterId ? { ...chapter, title } : chapter,
  )
}

const chapterSelectOptions = computed(() =>
  skeletonChapters.value.map((chapter) => ({
    label: chapter.title,
    value: chapter.chapter_id,
  })),
)

function handleMinPagesUpdate(value: number | null) {
  form.target_pages_min = value ?? 3
  if (
    form.target_pages_max === undefined ||
    form.target_pages_max < form.target_pages_min
  ) {
    form.target_pages_max = form.target_pages_min
  }
}

function handleMaxPagesUpdate(value: number | null) {
  form.target_pages_max = value ?? form.target_pages_min ?? 3
}

function normalizeRetrievalDepth(value: unknown): RetrievalDepth {
  if (value === 'L0' || value === 'L1' || value === 'L2') return value
  const text = String(value ?? '').toUpperCase()
  if (text.endsWith('.L0') || text.endsWith('L0')) return 'L0'
  if (text.endsWith('.L2') || text.endsWith('L2')) return 'L2'
  return 'L1'
}

function enterSkeletonView() {
  syncSkeletonFromTask()
  const runtimePolicy = task.value?.runtime?.retrieval_policy
  const depth = normalizeRetrievalDepth(runtimePolicy?.retrieval_depth ?? form.retrieval_depth)
  slideGenOptions.retrieval_depth = depth
  slideGenOptions.tavily_enabled = runtimePolicy?.tavily_enabled ?? true
  slideGenOptions.force_refresh = runtimePolicy?.force_refresh ?? false
  slideGenOptions.retrieval_policy = {
    retrieval_depth: depth,
    tavily_enabled: slideGenOptions.tavily_enabled,
    prefer_user_doc:
      runtimePolicy?.prefer_user_doc ??
      (Boolean(task.value?.input?.attachments?.length) ||
        task.value?.input?.source_type === 'long_document'),
    source_quality: (runtimePolicy?.source_quality ?? 'medium') as SourceQuality,
    force_refresh: slideGenOptions.force_refresh,
    enable_fallback_deepen: runtimePolicy?.enable_fallback_deepen ?? false,
  }
  view.value = 'skeleton'
}

function buildSlideGeneratePayload(): GenerateSlidesRequest {
  const depth = normalizeRetrievalDepth(slideGenOptions.retrieval_depth)
  const sourceQuality = (slideGenOptions.retrieval_policy.source_quality || 'medium') as SourceQuality
  const concurrency = [1, 2, 3].includes(Number(slideGenOptions.concurrency))
    ? (Number(slideGenOptions.concurrency) as 1 | 2 | 3)
    : 2
  const retrievalPolicy = {
    ...(slideGenOptions.retrieval_policy ?? {}),
    retrieval_depth: depth,
    tavily_enabled: Boolean(slideGenOptions.tavily_enabled),
    source_quality: sourceQuality,
    prefer_user_doc: Boolean(slideGenOptions.retrieval_policy.prefer_user_doc),
    force_refresh: Boolean(slideGenOptions.force_refresh),
    enable_fallback_deepen: Boolean(slideGenOptions.retrieval_policy.enable_fallback_deepen),
  }
  return {
    concurrency,
    force_refresh: Boolean(slideGenOptions.force_refresh),
    retrieval_depth: depth,
    tavily_enabled: Boolean(slideGenOptions.tavily_enabled),
    retrieval_policy: retrievalPolicy,
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
    task.value = await updateSkeleton(task.value.task_id, skeletonSlides.value, skeletonChapters.value)
    task.value = await generateSlides(task.value.task_id, buildSlideGeneratePayload())
    await pollTaskUntilSettled({
      done: (latestTask) => latestTask.status === 'done',
      onDone: (latestTask) => {
        if (latestTask.status === 'done') {
          outlineDraft.value = cloneOutline(latestTask.outline)
          saveMessage.value = ''
          view.value = 'result'
          void refreshTaskHistory()
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

  if (
    form.target_pages_min === undefined ||
    form.target_pages_max === undefined ||
    form.target_pages_min < 3 ||
    form.target_pages_max > 30 ||
    form.target_pages_min > form.target_pages_max
  ) {
    errorMessage.value = 'PPT 页数范围建议在 3 到 30 页之间，且最少页数不能大于最多页数'
    return false
  }

  if (form.source_type === 'long_document' && !(form.document_text ?? '').trim()) {
    errorMessage.value = '选择“长文档”时，请上传 .txt/.md 文件或粘贴文档正文'
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
    syncAnswersFromTask()
    void refreshTaskHistory()
    if (task.value.runtime?.document_analysis_status === 'running') {
      void pollDocumentAnalysis(task.value.task_id)
    }

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
          if (latestTask.status === 'failed') {
            errorMessage.value = latestTask.error?.message || '任务处理失败，可检查错误详情后重试。'
          }
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

async function pollDocumentAnalysis(taskId: string) {
  const startedAt = Date.now()
  const maxWaitMs = 90 * 1000
  let pollingInFlight = false

  const timer = window.setInterval(() => {
    if (pollingInFlight) return
    void (async () => {
      pollingInFlight = true
      try {
        if (!task.value || task.value.task_id !== taskId) {
          window.clearInterval(timer)
          return
        }
        const latestTask = await getTask(taskId)
        task.value = latestTask
        syncAnswersFromTask()
        const status = latestTask.runtime?.document_analysis_status
        const questionsReady = (latestTask.clarification?.questions?.length ?? 0) > 0
        if (
          ((status === 'done' || status === 'failed') && questionsReady) ||
          Date.now() - startedAt > maxWaitMs
        ) {
          window.clearInterval(timer)
        }
      } catch {
        window.clearInterval(timer)
      } finally {
        pollingInFlight = false
      }
    })()
  }, 1800)
}

function cloneOutline(outline: Task['outline']) {
  return outline ? JSON.parse(JSON.stringify(outline)) : null
}

function syncAnswersFromTask() {
  Object.keys(answers).forEach((key) => delete answers[key])
  task.value?.clarification?.questions.forEach((question) => {
    answers[question.question_id] = question.answer ?? ''
  })
}

async function refreshTaskHistory() {
  historyLoading.value = true
  try {
    const result = await listTasks(8)
    taskHistory.value = result.tasks
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '加载历史任务失败'
  } finally {
    historyLoading.value = false
  }
}

async function openTask(taskId: string) {
  loading.value = true
  errorMessage.value = ''
  try {
    const latestTask = await getTask(taskId)
    task.value = latestTask
    syncAnswersFromTask()
    syncSkeletonFromTask()
    if (
      latestTask.input?.source_type === 'long_document' &&
      (latestTask.runtime?.document_analysis_status === 'running' ||
        !(latestTask.clarification?.questions?.length ?? 0))
    ) {
      void pollDocumentAnalysis(latestTask.task_id)
    }
    outlineDraft.value = cloneOutline(latestTask.outline)
    if (latestTask.status === 'done' && latestTask.outline) {
      view.value = 'result'
    } else if (latestTask.outline_skeleton?.length) {
      enterSkeletonView()
    } else if (latestTask.clarification) {
      view.value = 'status'
    } else {
      view.value = 'form'
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '打开历史任务失败'
  } finally {
    loading.value = false
  }
}

function isSupportedDocumentFile(file: File) {
  const name = file.name.toLowerCase()
  return name.endsWith('.txt') || name.endsWith('.md')
}

async function handleLongDocumentFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return

  if (!isSupportedDocumentFile(file)) {
    errorMessage.value = '仅支持上传 .txt 或 .md 文件'
    return
  }
  if (file.size > DOCUMENT_UPLOAD_MAX_BYTES) {
    errorMessage.value = `文档过大，请控制在 ${Math.floor(DOCUMENT_UPLOAD_MAX_BYTES / 1_000_000)}MB 以内`
    return
  }

  readingLongDocument.value = true
  errorMessage.value = ''
  try {
    const text = await file.text()
    if (!text.trim()) {
      errorMessage.value = '上传的文档为空'
      return
    }
    form.document_text = text
    longDocumentFileName.value = file.name
    if (!(form.document_title ?? '').trim()) {
      form.document_title = file.name.replace(/\.(txt|md)$/i, '')
    }
  } catch {
    errorMessage.value = '读取文档失败，请重试'
  } finally {
    readingLongDocument.value = false
  }
}

function clearLongDocumentFile() {
  longDocumentFileName.value = ''
  form.document_text = ''
}

async function handleUploadDocument(file: File) {
  if (!task.value) return
  uploadingDocument.value = true
  errorMessage.value = ''
  try {
    await uploadTaskDocument(task.value.task_id, file)
    task.value = await getTask(task.value.task_id)
    if (slideGenOptions.retrieval_policy) {
      slideGenOptions.retrieval_policy.prefer_user_doc = true
    }
    saveMessage.value = '文档已上传，按页生成时将优先使用该材料。'
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '上传文档失败'
  } finally {
    uploadingDocument.value = false
  }
}

onMounted(() => {
  const token = localStorage.getItem('access_token')
  if (token) {
    loggedIn.value = true
    currentUsername.value = localStorage.getItem('username') || ''
  }
  if (loggedIn.value) {
    void refreshTaskHistory()
  }
})

function handleLoggedIn(username: string) {
  loggedIn.value = true
  currentUsername.value = username
  void refreshTaskHistory()
}

function handleLogout() {
  localStorage.removeItem('access_token')
  localStorage.removeItem('username')
  localStorage.removeItem('role')
  loggedIn.value = false
  currentUsername.value = ''
  view.value = 'form'
  task.value = null
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
    void refreshTaskHistory()
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
    task.value = await updateSkeleton(task.value.task_id, skeletonSlides.value, skeletonChapters.value)
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

function addSkeletonSlide() {
  const next = skeletonSlides.value.length + 1
  const chapterId = skeletonChapters.value[0]?.chapter_id ?? 'ch1'
  if (!skeletonChapters.value.length) {
    skeletonChapters.value = [{ chapter_id: chapterId, title: '默认章节', slide_ids: [] }]
  }
  const slideId = `s${next}`
  skeletonSlides.value.push({
    chapter_id: chapterId,
    slide_id: slideId,
    title: `新增页面 ${next}`,
    intent: '',
    user_notes: '',
  })
  skeletonChapters.value = skeletonChapters.value.map((chapter) =>
    chapter.chapter_id === chapterId
      ? { ...chapter, slide_ids: [...chapter.slide_ids, slideId] }
      : chapter,
  )
}

function removeSkeletonSlide(index: number) {
  const [removed] = skeletonSlides.value.splice(index, 1)
  if (removed) {
    skeletonChapters.value = skeletonChapters.value
      .map((chapter) => ({
        ...chapter,
        slide_ids: chapter.slide_ids.filter((slideId) => slideId !== removed.slide_id),
      }))
      .filter((chapter) => chapter.slide_ids.length > 0 || skeletonChapters.value.length === 1)
  }
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
  form.target_pages_min = 8
  form.target_pages_max = 12
  form.desired_chapters = ''
  form.language = 'zh'
  form.retrieval_depth = 'L1'
  form.raw_notes = ''
  form.document_title = ''
  form.document_text = ''
  longDocumentFileName.value = ''
  skeletonSlides.value = []
  skeletonChapters.value = []
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

async function handleDownloadPPTX() {
  if (!task.value) return
  const token = localStorage.getItem('access_token')
  const resp = await fetch(`/api/tasks/${task.value.task_id}/export/pptx`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}))
    errorMessage.value = (body as { error?: { message?: string } })?.error?.message ?? '导出 PPTX 失败'
    return
  }
  const blob = await resp.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${task.value.outline?.title || 'outline'}.pptx`
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
  <LoginView v-if="!loggedIn" @logged-in="handleLoggedIn" />
  <n-config-provider v-else :theme-overrides="{ common: { primaryColor: '#2864d8' } }">
    <n-message-provider>
      <div class="app-shell">
        <div class="app-topbar">
          <strong class="app-title">PPT Outline</strong>
          <n-steps :current="currentStep" size="small" class="header-steps">
            <n-step title="基本信息" />
            <n-step title="回答问题" />
            <n-step title="确认骨架" />
            <n-step title="查看大纲" />
          </n-steps>
          <n-space :size="8" align="center">
            <n-button v-if="currentUsername === 'admin' && currentPage === 'eval'" text size="small" @click="currentPage = 'workflow'">返回工作台</n-button>
            <n-button v-if="currentUsername === 'admin' && currentPage === 'workflow'" text size="small" @click="currentPage = 'eval'">评测</n-button>
            <n-text depth="3" style="font-size:12px">{{ currentUsername }}</n-text>
            <n-button text size="small" @click="handleLogout">退出</n-button>
            <n-tag size="small" :bordered="false" type="info">{{ apiModeLabel }}</n-tag>
          </n-space>
        </div>

        <div class="app-body" :style="{ overflow: currentPage === 'eval' ? 'auto' : 'hidden' }">
          <!-- Form -->
          <div v-if="view === 'form'" class="workflow-layout">
            <n-card title="创建演示任务" size="small" class="view-card">
              <n-grid :cols="2" :x-gap="16" :y-gap="0">
              <n-gi :span="2">
                <span class="label-text">PPT 主题 *</span>
                <n-input v-model:value="form.topic" placeholder="例如：基于 RAG 的 PPT 大纲智能生成系统" />
              </n-gi>
              <n-gi>
                <span class="label-text">输入类型</span>
                <n-select v-model:value="form.source_type" :options="[
                  { label: '短主题', value: 'short_topic' },
                  { label: '长文档', value: 'long_document' },
                ]" />
              </n-gi>
              <n-gi>
                <span class="label-text">演示时长（分钟）</span>
                <n-input-number v-model:value="form.duration_minutes" :min="5" :max="120" />
              </n-gi>
              <n-gi>
                <span class="label-text">最少页数 *</span>
                <n-input-number
                  :value="form.target_pages_min"
                  :min="3"
                  :max="30"
                  @update:value="handleMinPagesUpdate"
                />
              </n-gi>
              <n-gi>
                <span class="label-text">最多页数 *</span>
                <n-input-number
                  v-model:value="form.target_pages_max"
                  :min="form.target_pages_min ?? 3"
                  :max="30"
                  @update:value="handleMaxPagesUpdate"
                />
              </n-gi>
              <n-gi>
                <span class="label-text">听众 / 场景</span>
                <n-input v-model:value="form.audience" placeholder="课程答辩、产品汇报…" />
              </n-gi>
              <n-gi>
                <span class="label-text">检索深度</span>
                <n-select v-model:value="form.retrieval_depth" :options="[
                  { label: 'L0：轻量（资料少查）', value: 'L0' },
                  { label: 'L1：平衡（默认）', value: 'L1' },
                  { label: 'L2：深度（多查引用）', value: 'L2' },
                ]" />
              </n-gi>
              <n-gi :span="2">
                <span class="label-text">补充材料</span>
                <n-input v-model:value="form.raw_notes" type="textarea" :rows="2"
                  placeholder="可以粘贴老师要求、参考资料、已有的想法" />
              </n-gi>
              <n-gi :span="2">
                <span class="label-text">期望章节（可选）</span>
                <n-input
                  v-model:value="form.desired_chapters"
                  placeholder="例如：背景、方案、实现、评估、总结"
                />
              </n-gi>
            </n-grid>
            <template v-if="form.source_type === 'long_document'">
              <n-grid :cols="1" style="margin-top:12px">
                <n-gi>
                  <span class="label-text">文档标题（可选）</span>
                  <n-input v-model:value="form.document_title" placeholder="RAG 在教学场景中的应用研究" />
                </n-gi>
                <n-gi>
                  <span class="label-text">文档正文 *</span>
                  <label :class="['upload-box', { disabled: readingLongDocument }]">
                    <input
                      type="file"
                      accept=".txt,.md"
                      :disabled="readingLongDocument"
                      @change="handleLongDocumentFile"
                    />
                    {{ readingLongDocument ? '正在读取文档…' : '上传 .txt / .md 作为正文' }}
                  </label>
                  <n-text v-if="longDocumentFileName" depth="3" class="field-hint">
                    已选择：{{ longDocumentFileName }}
                    <n-button text type="primary" size="tiny" @click="clearLongDocumentFile">清除</n-button>
                  </n-text>
                  <n-input
                    v-model:value="form.document_text"
                    type="textarea"
                    :rows="6"
                    placeholder="也可直接粘贴长文档正文；上传后会自动填入这里"
                    style="margin-top: 8px"
                  />
                  <n-text depth="3" class="field-hint">
                    当前正文约 {{ form.document_text?.length ?? 0 }} 字，创建后会同步建立任务级 RAG 索引
                  </n-text>
                </n-gi>
              </n-grid>
              </template>
            </n-card>
            <TaskSidebar
              :tasks="taskHistory"
              :history-loading="historyLoading"
              show-history
              @refresh-history="refreshTaskHistory"
              @open-task="openTask"
              @upload-document="handleUploadDocument"
            />
          </div>

          <!-- Status -->
          <n-card
            v-if="view === 'status' && task"
            :title="isDocumentAnalyzing ? '正在分析文档' : '回答问题'"
            size="small"
            class="view-card"
          >
            <n-space vertical :size="12">
              <n-tag type="info">{{ statusText }}</n-tag>
              <n-card
                v-if="task.input?.source_type === 'long_document'"
                size="small"
                embedded
                :title="isDocumentAnalyzing ? '文档摘要中' : '文档分析结果'"
              >
                <n-space vertical :size="6">
                  <n-text v-if="isDocumentAnalyzing">
                    状态：{{ documentAnalysisStatusLabel }}
                  </n-text>
                  <n-text
                    v-if="isDocumentAnalyzing || documentAnalysisText"
                    :depth="isDocumentAnalyzing ? 2 : 3"
                    class="field-hint"
                  >
                    {{ documentAnalysisText }}
                  </n-text>
                  <n-text v-if="!isDocumentAnalyzing && task.input?.document_profile?.summary" depth="3">
                    {{ task.input.document_profile.summary }}
                  </n-text>
                  <n-text v-else-if="!isDocumentAnalyzing" depth="3">
                    已读取文档规则画像，后端会在生成时使用文档重点。
                  </n-text>
                </n-space>
              </n-card>
              <n-card v-if="isDocumentAnalyzing" size="small" embedded>
                <n-space align="center" :size="10">
                  <n-spin size="small" />
                  <n-text depth="3">摘要完成后将自动展示澄清问题，无需手动刷新。</n-text>
                </n-space>
              </n-card>
              <div v-else-if="clarificationReady && task.clarification">
                <n-grid :cols="1" :y-gap="8">
                  <n-gi v-for="q in task.clarification.questions" :key="q.question_id">
                    <n-space vertical :size="6">
                      <n-space align="center" :size="8">
                        <n-text strong>{{ q.prompt }}</n-text>
                        <n-tag v-if="q.answer" type="success" size="small">
                          已预填
                        </n-tag>
                      </n-space>

                      <n-text v-if="q.answer" depth="3" class="field-hint">
                        建议答案：{{ q.answer }}
                      </n-text>

                      <n-input
                        v-model:value="answers[q.question_id!]"
                        type="textarea"
                        :rows="2"
                        placeholder="请根据你的演示目标补充或修改答案"
                      />
                    </n-space>
                  </n-gi>
                </n-grid>
              </div>
            </n-space>
          </n-card>

          <!-- Skeleton -->
          <n-card v-if="view === 'skeleton' && task" title="确认骨架" size="small" class="view-card">
            <n-space vertical :size="12">
              <n-tag type="info">{{ statusText }}</n-tag>
              <div v-if="!skeletonSlides.length" style="text-align:center;padding:32px 0">
                <n-text depth="3">提交澄清后先生成 PPT 页级骨架，确认每页主题后再按页生成完整内容。</n-text>
                <br/>
                <n-button :loading="loading || task.status === 'generating'"
                  @click="handleGenerateSkeleton" style="margin-top:12px">
                  {{ task.status === 'generating' ? '骨架生成中…' : '生成骨架' }}
                </n-button>
              </div>
              <div v-else>
                <div v-if="skeletonChapterGroups.length" class="chapter-hint">
                  <strong>章节结构</strong>
                  <n-grid :cols="2" :x-gap="12" :y-gap="8" class="chapter-editor">
                    <n-gi
                      v-for="chapter in skeletonChapters"
                      :key="chapter.chapter_id"
                    >
                      <span class="label-text">{{ chapter.chapter_id }} · {{ chapter.slide_ids.length }} 页</span>
                      <n-input
                        :value="chapter.title"
                        size="small"
                        placeholder="章节标题"
                        @update:value="(value) => updateChapterTitle(chapter.chapter_id, value)"
                      />
                    </n-gi>
                  </n-grid>
                  <n-text depth="3" class="field-hint">
                    章节名和每页所属章节会随最终大纲保留。
                  </n-text>
                </div>
                <n-grid :cols="2" :x-gap="12" :y-gap="12">
                  <n-gi v-for="(slide, idx) in skeletonSlides" :key="slide.slide_id">
                    <n-card size="small" :title="`第 ${idx + 1} 页`" embedded>
                      <template #header-extra>
                        <n-button text type="error" size="tiny" @click="removeSkeletonSlide(idx)">删除</n-button>
                      </template>
                      <n-space vertical :size="8">
                        <n-select
                          :value="slide.chapter_id ?? skeletonChapters[0]?.chapter_id"
                          :options="chapterSelectOptions"
                          size="small"
                          placeholder="选择所属章节"
                          @update:value="(value) => assignSlideToChapter(slide.slide_id, String(value))"
                        />
                        <n-input v-model:value="slide.title" placeholder="页面标题" size="small" />
                        <n-input v-model:value="slide.intent" type="textarea" :rows="2" placeholder="页面意图" size="small" />
                        <n-input v-model:value="slide.user_notes" type="textarea" :rows="2" placeholder="补充要求" size="small" />
                      </n-space>
                    </n-card>
                  </n-gi>
                </n-grid>
                <n-collapse style="margin-top:12px">
                  <n-collapse-item title="高级选项（按页生成参数）" name="generation-options">
                    <n-grid :cols="4" :x-gap="12" :y-gap="12">
                      <n-gi>
                        <span class="label-text">检索深度</span>
                        <n-select
                         v-model:value="slideGenOptions.retrieval_depth"
                          size="small"
                          :options="[
                            { label: '资料少查（速度优先）', value: 'L0' },
                            { label: '平衡模式（推荐）', value: 'L1' },
                            { label: '多查引用（资料更充分）', value: 'L2' },
                          ]"
                        />
                      </n-gi>

                      <n-gi>
                        <span class="label-text">并发数</span>
                        <n-select
                         v-model:value="slideGenOptions.concurrency"
                         size="small"
                          :options="[
                            { label: '1（最稳）', value: 1 },
                            { label: '2（推荐）', value: 2 },
                            { label: '3（最快）', value: 3 },
                         ]"
                       />
                      </n-gi>

                      <n-gi>
                        <span class="label-text">来源质量</span>
                        <n-select
                          v-model:value="slideGenOptions.retrieval_policy.source_quality"
                          size="small"
                          :options="[
                            { label: '宽松', value: 'low' },
                            { label: '平衡', value: 'medium' },
                            { label: '高质量优先', value: 'high' },
                          ]"
                        />
                      </n-gi>

                      <n-gi style="display:flex;align-items:flex-end">
                       <n-checkbox
                         v-model:checked="slideGenOptions.tavily_enabled"
                         @update:checked="(value) => { slideGenOptions.retrieval_policy.tavily_enabled = value }"
                       >
                         联网检索
                        </n-checkbox>
                       </n-gi>

                      <n-gi style="display:flex;align-items:flex-end">
                       <n-checkbox
                         v-model:checked="slideGenOptions.force_refresh"
                         @update:checked="(value) => { slideGenOptions.retrieval_policy.force_refresh = value }"
                       >
                         强制刷新
                        </n-checkbox>
                       </n-gi>

                      <n-gi style="display:flex;align-items:flex-end">
                       <n-checkbox v-model:checked="slideGenOptions.retrieval_policy.prefer_user_doc">
                         优先我的文档
                        </n-checkbox>
                       </n-gi>

                      <n-gi style="display:flex;align-items:flex-end">
                       <n-checkbox v-model:checked="slideGenOptions.retrieval_policy.enable_fallback_deepen">
                         证据不足时加深
                        </n-checkbox>
                       </n-gi>
                      </n-grid>

                      <n-text depth="3" class="field-hint">
                        这些选项会随请求写入 runtime.retrieval_policy，并影响按页检索与单页重做。
                      </n-text>
                    </n-collapse-item>
                    </n-collapse>
                <TaskSidebar
                  :task="task"
                  :uploading="uploadingDocument"
                  :upload-disabled="task.status === 'generating'"
                  @upload-document="handleUploadDocument"
                />
              </div>
              <div v-if="task.status === 'failed'" class="error-box">
                <n-text type="error">{{ taskErrorLabel }} — {{ task.error?.message }}</n-text>
                <ul v-if="taskErrorDetails.length" class="error-detail-list">
                  <li v-for="item in taskErrorDetails" :key="item">{{ item }}</li>
                </ul>
                <n-text depth="3" class="field-hint">
                  可修改骨架或调整高级选项后再次点击“按页生成”。
                </n-text>
              </div>
            </n-space>
          </n-card>

          <!-- Result -->
          <div v-if="view === 'result' && outlineDraft" style="height:100%">
            <div style="margin-bottom:12px">
              <n-input v-model:value="outlineDraft.title" size="large" placeholder="整稿标题" />
            </div>
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
              <TaskSidebar
                :task="task"
                :tasks="taskHistory"
                :history-loading="historyLoading"
                :uploading="uploadingDocument"
                :upload-disabled="task?.status === 'generating'"
                show-history
                @refresh-history="refreshTaskHistory"
                @open-task="openTask"
                @upload-document="handleUploadDocument"
              />
            </div>
          </div>
          <div v-if="currentPage === 'eval'" style="flex:1;overflow-y:auto">
            <EvalView />
          </div>
        </div>

        <div v-if="currentPage === 'workflow'" class="app-bottombar">
          <div class="footer-hint">
            <n-text v-if="footerHint" depth="3" class="footer-msg">{{ footerHint }}</n-text>
          </div>
          <div class="footer-actions">
            <n-button v-if="view !== 'form'" @click="restart" secondary>重新开始</n-button>
            <n-button v-if="view === 'form'" type="primary" :loading="loading" @click="handleCreateTask">
              {{ loading ? '创建中…' : '下一步：回答问题' }}
            </n-button>
            <n-button
              v-if="view === 'status' && clarificationReady && task?.clarification && !task.clarification.submitted"
              type="primary"
              :loading="loading"
              @click="handleSubmitClarification"
            >提交澄清</n-button>
            <n-button v-if="view === 'status' && task?.clarification?.submitted"
              type="primary" @click="enterSkeletonView">继续：确认骨架</n-button>
            <n-button v-if="view === 'skeleton' && skeletonSlides.length"
              @click="addSkeletonSlide" secondary>+ 新增</n-button>
            <n-button v-if="view === 'skeleton' && skeletonSlides.length"
              :loading="loading" @click="handleSaveSkeleton" secondary>保存骨架</n-button>
            <n-button v-if="view === 'skeleton' && skeletonSlides.length"
              type="primary" :loading="loading || task?.status === 'generating'"
              @click="handleGenerateSlides">按页生成</n-button>
            <n-button v-if="view === 'result'" type="primary" :loading="savingOutline"
              @click="handleSaveOutline">保存修改</n-button>
            <n-button v-if="view === 'result'" @click="handleCopyMarkdown" secondary>复制 Markdown</n-button>
            <n-button v-if="view === 'result'" @click="handleDownloadMarkdown" secondary>下载 .md</n-button>
            <n-button v-if="view === 'result'" @click="handleDownloadPPTX" secondary>下载 .pptx</n-button>
          </div>
        </div>
      </div>

      <n-modal v-if="showIncrementalOutline && task" :show="true" preset="card"
        title="正在生成大纲" style="width:min(780px,95vw)" :mask-closable="true"
        @update:show="() => {}">
        <GeneratingView :task="task" :slides="incrementalSlides" @close="() => {}" />
      </n-modal>
    </n-message-provider>
  </n-config-provider>
</template>

<style scoped>
.app-shell {
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.app-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  height: 48px;
  gap: 24px;
  border-bottom: 1px solid #e3e8f0;
  background: #fff;
  flex-shrink: 0;
}
.app-topbar .app-title {
  font-size: 16px;
  font-weight: 700;
  white-space: nowrap;
}
.header-steps {
  flex: 1;
  max-width: 560px;
}
.app-body {
  flex: 1;
  overflow: hidden;
  padding: 16px 24px;
  background: #f5f7fa;
}
.view-card {
  max-width: 800px;
  margin: 0 auto;
  max-height: calc(100vh - 150px);
  overflow-y: auto;
  padding: 0 4px 72px 0;
  box-sizing: border-box;
}
.workflow-layout {
  display: grid;
  grid-template-columns: minmax(0, 800px) 240px;
  gap: 24px;
  justify-content: center;
  align-items: start;
  height: calc(100vh - 150px);
  overflow: hidden;
}
.workflow-layout .view-card {
  width: 100%;
  margin: 0;
}
.app-bottombar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  height: 56px;
  gap: 12px;
  border-top: 1px solid #e3e8f0;
  background: #fff;
  flex-shrink: 0;
}
.footer-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}
.footer-hint {
  flex: 1;
  min-width: 0;
  overflow: hidden;
}
.footer-msg {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: block;
}
.result-body {
  display: grid;
  grid-template-columns: 1fr 240px;
  gap: 24px;
  align-items: start;
  height: calc(100vh - 150px);
  overflow: hidden;
}
.result-body > :first-child {
  overflow-y: auto;
  max-height: calc(100vh - 150px);
  padding: 0 12px 72px 0;
  box-sizing: border-box;
}
.error-box {
  padding: 12px 16px;
  border-radius: 8px;
  background: #fff5f5;
  border: 1px solid #fecaca;
}
.error-detail-list {
  margin: 8px 0 0;
  padding-left: 18px;
  color: #b42318;
  font-size: 13px;
  line-height: 1.6;
}
.chapter-hint {
  margin-bottom: 12px;
  padding: 12px;
  border-radius: 10px;
  background: #f7f9fc;
  border: 1px solid #e3e8f0;
}

.upload-box {
  display: block;
  padding: 10px 12px;
  border: 1px dashed #9db7e8;
  border-radius: 10px;
  background: #f7faff;
  color: #1f4eb0;
  text-align: center;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.upload-box input {
  display: none;
}

.upload-box.disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.chapter-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 8px 0 4px;
}
.chapter-tag {
  padding: 4px 9px;
  border-radius: 999px;
  background: #eaf1ff;
  color: #1f4eb0;
  font-size: 12px;
  font-weight: 600;
}
.label-text {
  display: block;
  margin-bottom: 4px;
  font-size: 13px;
  color: #666;
}
@media (max-width: 900px) {
  .result-body { grid-template-columns: 1fr; }
  .workflow-layout { grid-template-columns: 1fr; overflow-y: auto; }
  .header-steps { display: none; }
}
</style>
