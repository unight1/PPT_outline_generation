<script setup lang="ts">
import type { Task, TaskListItem } from '../types/task'

const props = defineProps<{
  showHistory?: boolean
  task?: Task | null
  tasks?: TaskListItem[]
  uploadDisabled?: boolean
  historyLoading?: boolean
  uploading?: boolean
}>()

const emit = defineEmits<{
  (e: 'new-task'): void
  (e: 'open-task', taskId: string): void
  (e: 'refresh-history'): void
  (e: 'upload-document', file: File): void
  (e: 'delete-task', taskId: string): void
  (e: 'search-task', keyword: string): void
}>()

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) {
    emit('upload-document', file)
    input.value = ''
  }
}

function statusLabel(status?: string | null) {
  if (status === 'done') return '完成'
  if (status === 'failed') return '失败'
  if (status === 'running') return '分析中'
  if (status === 'pending') return '等待中'
  return status || '未开始'
}

function taskTitle(item: TaskListItem) {
  return item.input?.topic || item.task_id
}

const hasAttachments = () => Boolean(props.task?.input?.attachments?.length)
</script>

<template>
  <aside class="sidebar">
    <div v-if="showHistory" class="section">
      <div class="section-head">
        <strong class="section-title">最近任务</strong>
        <button class="link-btn" type="button" :disabled="historyLoading" @click="$emit('refresh-history')">
          刷新
        </button>
      </div>
      <div class="search-box">
        <input
          class="search-input"
          type="text"
          placeholder="搜索任务…"
          @input="$emit('search-task', ($event.target as HTMLInputElement).value)"
        />
      </div>
      <div v-if="tasks?.length" class="history-list">
        <div
          v-for="item in tasks"
          :key="item.task_id"
          class="history-item"
          @click="$emit('open-task', item.task_id)"
        >
          <span class="history-title">{{ taskTitle(item) }}</span>
          <span class="history-meta">{{ statusLabel(item.status) }} · {{ item.updated_at.slice(0, 10) }}</span>
          <button class="delete-btn" type="button" @click.stop="$emit('delete-task', item.task_id)" title="删除">✕</button>
        </div>
      </div>
      <div v-else-if="historyLoading" class="skeleton-list">
        <div v-for="n in 3" :key="n" class="skeleton-row">
          <div class="skeleton-line w-80" />
          <div class="skeleton-line w-50" />
        </div>
      </div>
      <p v-else class="empty-state">
        <span class="empty-icon">📋</span>
        <span class="empty-text">暂无任务，创建第一个吧</span>
      </p>
    </div>

    <div v-if="task?.input?.source_type === 'long_document' || task?.input?.document_profile" class="section">
      <strong class="section-title">文档分析</strong>
      <p class="hint">
        状态：{{ statusLabel(task?.runtime?.document_analysis_status) }}
      </p>
      <p v-if="task?.input?.document_profile?.summary" class="summary-text">
        {{ task.input.document_profile.summary }}
      </p>
      <div v-if="task?.input?.document_profile?.key_points?.length" class="chips">
        <span
          v-for="point in task.input.document_profile.key_points.slice(0, 3)"
          :key="point"
          class="mini-chip"
        >
          {{ point }}
        </span>
      </div>
    </div>

    <div v-if="task" class="section">
      <strong class="section-title">上传文档</strong>
      <label :class="['upload-box', { disabled: uploadDisabled || uploading }]">
        <input
          type="file"
          accept=".txt,.md,.pdf"
          :disabled="uploadDisabled || uploading"
          @change="onFileChange"
        />
        {{ uploading ? '上传处理中…' : '上传 .txt / .md' }}
      </label>
      <div v-if="hasAttachments()" class="attachment-list">
        <div
          v-for="attachment in task.input?.attachments"
          :key="attachment.document_id"
          class="attachment-item"
        >
          <span>{{ attachment.filename }}</span>
          <small>{{ statusLabel(attachment.status) }} · {{ attachment.chunk_count ?? 0 }} 块</small>
        </div>
      </div>
      <p v-else class="hint empty-text">上传参考材料后，按页生成可优先使用你的文档。</p>
    </div>

    <div v-if="task" class="section">
      <strong class="section-title">高级检索</strong>
      <p class="hint">
        深度：{{ task?.runtime?.retrieval_policy?.retrieval_depth ?? task?.input?.retrieval_depth ?? 'L1' }}
      </p>
      <p class="hint">
        优先文档：{{ task?.runtime?.retrieval_policy?.prefer_user_doc ? '开启' : '关闭' }}
      </p>
      <p class="hint">
        来源质量：{{ task?.runtime?.retrieval_policy?.source_quality ?? 'medium' }}
      </p>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  padding: 16px;
  border-left: 1px solid #e3e8f0;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.section {
  padding-bottom: 16px;
}

.section + .section {
  border-top: 1px solid #e3e8f0;
  padding-top: 16px;
}

.section-title {
  display: block;
  font-size: 13px;
  font-weight: 700;
  color: #5d6b82;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 10px;
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.link-btn {
  border: 0;
  background: none;
  color: #2864d8;
  cursor: pointer;
  font-size: 12px;
}

.history-list,
.attachment-list,
.chips {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.history-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
  border: 1px solid #e3e8f0;
  border-radius: 8px;
  background: #fbfcff;
  text-align: left;
  cursor: pointer;
  position: relative;
}

.history-item:hover {
  border-color: #2864d8;
}

.history-title,
.attachment-item span {
  font-size: 13px;
  font-weight: 600;
  color: #172033;
}

.history-meta,
.attachment-item small {
  font-size: 12px;
  color: #5d6b82;
}

.summary-text {
  margin: 6px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: #334155;
}

.mini-chip {
  padding: 5px 8px;
  border-radius: 999px;
  background: #eaf1ff;
  color: #1f4eb0;
  font-size: 12px;
  line-height: 1.35;
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

.attachment-item {
  display: flex;
  flex-direction: column;
  padding: 8px 10px;
  border-radius: 8px;
  background: #f7f9fc;
}

.empty-text {
  font-size: 12px;
  font-style: italic;
}

.hint {
  color: #5d6b82;
  font-size: 13px;
}

.delete-btn {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  color: #a0a8b8;
  cursor: pointer;
  font-size: 14px;
  padding: 2px 6px;
  border-radius: 4px;
  opacity: 0;
  transition: opacity 0.15s;
}
.history-item:hover .delete-btn {
  opacity: 1;
}
.delete-btn:hover {
  color: #e04040;
  background: #ffeaea;
}

.search-box {
  margin-bottom: 8px;
}
.search-input {
  width: 100%;
  padding: 6px 10px;
  border: 1px solid #d9dfe8;
  border-radius: 6px;
  font-size: 12px;
  outline: none;
  box-sizing: border-box;
}
.search-input:focus {
  border-color: #2864d8;
}

.skeleton-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 4px 0;
}
.skeleton-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 10px;
  border-radius: 8px;
  background: #f0f3f7;
}
.skeleton-line {
  height: 12px;
  border-radius: 4px;
  background: linear-gradient(90deg, #e0e4ea 25%, #f0f3f7 50%, #e0e4ea 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
}
.skeleton-line.w-80 { width: 80%; }
.skeleton-line.w-50 { width: 50%; }

@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 16px 0;
  color: #a8b0c0;
  text-align: center;
}
.empty-icon {
  font-size: 28px;
  opacity: 0.6;
}
.empty-text {
  font-size: 12px;
}
</style>
