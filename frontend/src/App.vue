<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
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
  <n-config-provider :theme-overrides="{ common: { primaryColor: '#2864d8' } }">
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
          <n-tag size="small" :bordered="false" type="info">{{ apiModeLabel }}</n-tag>
        </div>

        <div class="app-body">
          <!-- Form -->
          <n-card v-if="view === 'form'" title="创建演示任务" size="small" class="view-card">
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
            </n-grid>
            <template v-if="form.source_type === 'long_document'">
              <n-grid :cols="1" style="margin-top:12px">
                <n-gi>
                  <span class="label-text">文档标题（可选）</span>
                  <n-input v-model:value="form.document_title" placeholder="RAG 在教学场景中的应用研究" />
                </n-gi>
                <n-gi>
                  <span class="label-text">文档正文 *</span>
                  <n-input v-model:value="form.document_text" type="textarea" :rows="5"
                    placeholder="请粘贴长文档正文，后端将用于提炼重点与生成大纲" />
                
                  <n-text depth="3" class="field-hint">
                     当前正文约 {{ form.document_text?.length ?? 0 }} 字
                  </n-text>
                  </n-gi> 
              </n-grid>
            </template>
          </n-card>

          <!-- Status -->
          <n-card v-if="view === 'status' && task" title="回答问题" size="small" class="view-card">
            <n-space vertical :size="12">
              <n-tag type="info">{{ statusText }} · {{ task.task_id }}</n-tag>
              <div v-if="task.clarification">
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
                <n-grid :cols="2" :x-gap="12" :y-gap="12">
                  <n-gi v-for="(slide, idx) in skeletonSlides" :key="slide.slide_id">
                    <n-card size="small" :title="`第 ${idx + 1} 页`" embedded>
                      <template #header-extra>
                        <n-button text type="error" size="tiny" @click="removeSkeletonSlide(idx)">删除</n-button>
                      </template>
                      <n-space vertical :size="8">
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

                     <n-gi style="display:flex;align-items:flex-end">
                       <n-checkbox v-model:checked="slideGenOptions.tavily_enabled">
                         联网检索
                        </n-checkbox>
                       </n-gi>

                      <n-gi style="display:flex;align-items:flex-end">
                       <n-checkbox v-model:checked="slideGenOptions.force_refresh">
                         强制刷新
                        </n-checkbox>
                       </n-gi>
                      </n-grid>

                      <n-text depth="3" class="field-hint">
                        这些选项会影响按页生成阶段；当前可先用于 Mock / 本地状态，真实 retrieval policy 由后续对接接入。
                      </n-text>
                    </n-collapse-item>
                    </n-collapse>
              </div>
              <div v-if="task.status === 'failed'" class="error-box">
                <n-text type="error">{{ taskErrorLabel }} — {{ task.error?.message }}</n-text>
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
              <TaskSidebar show-history />
            </div>
          </div>
        </div>

        <div class="app-bottombar">
          <div class="footer-hint">
            <n-text v-if="footerHint" depth="3" class="footer-msg">{{ footerHint }}</n-text>
          </div>
          <div class="footer-actions">
            <n-button v-if="view !== 'form'" @click="restart" secondary>重新开始</n-button>
            <n-button v-if="view === 'form'" type="primary" :loading="loading" @click="handleCreateTask">
              {{ loading ? '创建中…' : '下一步：回答问题' }}
            </n-button>
            <n-button v-if="view === 'status' && task?.clarification && !task.clarification.submitted"
              type="primary" :loading="loading" @click="handleSubmitClarification">提交澄清</n-button>
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
  padding-right: 4px;
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
  padding-right: 12px;
}
.error-box {
  padding: 12px 16px;
  border-radius: 8px;
  background: #fff5f5;
  border: 1px solid #fecaca;
}
.label-text {
  display: block;
  margin-bottom: 4px;
  font-size: 13px;
  color: #666;
}
@media (max-width: 900px) {
  .result-body { grid-template-columns: 1fr; }
  .header-steps { display: none; }
}
</style>
