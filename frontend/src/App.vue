<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import type { CreateTaskRequest, Task } from './types/task'
import {
  createTask,
  generateOutline,
  getTask,
  submitClarification,
  apiModeLabel,
} from './api'

type ViewName = 'form' | 'status' | 'result'

const view = ref<ViewName>('form')
const loading = ref(false)
const errorMessage = ref('')
const task = ref<Task | null>(null)

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
    errorMessage.value = '选择“长文档”时，需填写文档正文'
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
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '提交澄清失败'
  } finally {
    loading.value = false
  }
}

async function handleGenerate() {
  if (!task.value) return

  loading.value = true
  errorMessage.value = ''

  try {
    task.value = await generateOutline(task.value.task_id)
    const pollStart = Date.now()
    const maxPollMs = 15 * 60 * 1000
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
            loading.value = false

            if (latestTask.status === 'done') {
              view.value = 'result'
            }
          } else if (Date.now() - pollStart > maxPollMs) {
            window.clearInterval(timer)
            loading.value = false
            errorMessage.value = `轮询超时（当前状态：${latestTask.status}），请稍后刷新任务状态。`
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
  } catch (error) {
    loading.value = false
    errorMessage.value = error instanceof Error ? error.message : '生成失败'
  }
}

function restart() {
  view.value = 'form'
  task.value = null
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
}
</script>

<template>
  <main class="page">
    <section class="hero">
      <p class="eyebrow">PPT Outline Generation</p>
      <h1>智能 PPT 大纲生成前端 Demo</h1>
      <p class="subtitle">
        第 3–4 周 C 任务：需求澄清 -> 任务状态 -> 大纲结果展示。当前接口模式：{{ apiModeLabel }}。
      </p>
    </section>

    <section class="steps">
      <div :class="['step', view === 'form' && 'active']">1. 填写需求</div>
      <div :class="['step', view === 'status' && 'active']">2. 任务状态</div>
      <div :class="['step', view === 'result' && 'active']">3. 大纲结果</div>
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
          {{ loading ? '提交中...' : '提交澄清' }}
        </button>
      </div>

      <div class="actions">
        <button :disabled="loading" @click="handleGenerate">
          {{ task.status === 'generating' ? '生成中...' : '触发大纲生成' }}
        </button>

        <button class="secondary" @click="restart">重新开始</button>
      </div>

      <p v-if="task.status === 'generating'" class="hint">
        正在轮询后端任务状态，通常在数十秒到数分钟内完成（视模型与检索耗时而定）。
      </p>
    </section>

    <section v-if="view === 'result' && task?.outline" class="card">
      <div class="result-header">
        <div>
          <h2>{{ task.outline.title }}</h2>
          <p>
            检索深度：{{ task.outline.meta.retrieval_depth }} · 生成时间：
            {{ task.outline.meta.generated_at }}
          </p>
        </div>

        <button class="secondary" @click="restart">生成新的大纲</button>
      </div>

      <div class="outline">
        <article
          v-for="(slide, index) in task.outline.slides"
          :key="slide.slide_id"
          class="slide"
        >
          <h3>第 {{ index + 1 }} 页：{{ slide.title }}</h3>

          <ul>
            <li v-for="bullet in slide.bullets" :key="bullet.bullet_id">
              {{ bullet.text }}

              <span
                v-if="bullet.evidence_ids.length"
                class="evidence-tag"
              >
                证据：{{ bullet.evidence_ids.join(', ') }}
              </span>
            </li>
          </ul>

          <p v-if="slide.speaker_notes" class="notes">
            讲者备注：{{ slide.speaker_notes }}
          </p>
        </article>
      </div>

      <section class="evidence">
        <h3>证据目录</h3>

        <article
          v-for="evidence in task.outline.evidence_catalog"
          :key="evidence.evidence_id"
          class="evidence-card"
        >
          <strong>{{ evidence.evidence_id }}</strong>
          <p>{{ evidence.snippet }}</p>
          <small>
            来源：{{ evidence.source_id }} · 位置：{{ evidence.locator }} ·
            score：{{ evidence.score ?? '无' }} · confidence：{{ evidence.confidence ?? '无' }}
          </small>
        </article>
      </section>
    </section>
  </main>
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
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
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
}

.hint {
  color: #5d6b82;
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

.evidence {
  margin-top: 28px;
}

.evidence-card {
  margin-top: 12px;
  padding: 14px;
  border-radius: 12px;
  background: #f7f9fc;
}

.evidence-card p {
  margin: 8px 0;
}

.evidence-card small {
  color: #5d6b82;
}

@media (max-width: 720px) {
  .steps,
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
</style>