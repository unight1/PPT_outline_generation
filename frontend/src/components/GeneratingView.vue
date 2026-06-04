<script setup lang="ts">
import { computed } from 'vue'
import type { Task } from '../types/task'
import SlidePanel from './SlidePanel.vue'

const props = defineProps<{
  task: Task
  slides: Array<{
    slide_id: string
    title: string
    index: number
    slide: Task['outline'] extends { slides: (infer S)[] } | null ? (S | null) : never
    status: 'done' | 'generating' | 'failed'
  }>
}>()

defineEmits<{
  (e: 'close'): void
}>()

const completed = computed(() => props.slides.filter((s) => s.status === 'done').length)
const failed = computed(() => props.slides.filter((s) => s.status === 'failed').length)
const total = computed(() => props.slides.length)

const selectedIndex = ref(0)
const selectedSlide = computed(() => props.slides[selectedIndex.value])

function selectSlide(idx: number) {
  selectedIndex.value = idx
}

const progressMessage = computed(() => {
  return (
    props.task.progress?.message ||
    `已完成 ${completed.value} / ${total.value} 页` +
      (failed.value > 0 ? `，${failed.value} 页失败` : '')
  )
})
</script>

<script lang="ts">
import { ref } from 'vue'
</script>

<template>
  <div class="dialog-overlay" @click.self="$emit('close')">
    <div class="dialog-card">
      <div class="dialog-header">
        <strong>正在生成大纲…</strong>
        <button class="close-btn" type="button" @click="$emit('close')">✕</button>
      </div>

      <!-- Progress bar -->
      <div class="progress-section">
        <div class="status-summary">
          <span>{{ progressMessage }}</span>
          <span class="hint">阶段：{{ task.progress?.phase || 'processing' }}</span>
        </div>

        <div
          v-if="typeof task.progress?.percent === 'number'"
          class="progress-track"
        >
          <div
            class="progress-fill"
            :style="{ width: `${task.progress.percent}%` }"
          />
        </div>
      </div>

      <!-- Page status chips -->
      <div class="status-chips">
        <button
          v-for="item in slides"
          :key="item.slide_id"
          :class="[
            'status-chip',
            item.status,
            { active: item.index === selectedIndex },
          ]"
          @click="selectSlide(item.index)"
        >
          <span class="chip-idx">{{ item.index + 1 }}</span>
          <span class="chip-title">{{ item.title || item.slide_id }}</span>
          <span v-if="item.status === 'generating'" class="chip-dot pulse" />
          <span v-if="item.status === 'done'" class="chip-dot done" />
          <span v-if="item.status === 'failed'" class="chip-dot failed" />
        </button>
      </div>

      <!-- Selected page preview -->
      <div class="preview-section">
        <template v-if="selectedSlide?.slide">
          <SlidePanel
            :slide="selectedSlide.slide"
            :index="selectedSlide.index"
            :total="total"
            :editable="false"
          />
        </template>
        <div v-else class="empty-preview">
          <p v-if="selectedSlide?.status === 'generating'" class="hint">
            正在生成第 {{ selectedSlide.index + 1 }} 页内容，请稍候…
          </p>
          <p v-else-if="selectedSlide?.status === 'failed'" class="error">
            第 {{ selectedSlide.index + 1 }} 页生成失败
          </p>
          <p v-else class="hint">点击上方页签查看已完成的内容</p>
        </div>
      </div>

      <div class="dialog-footer">
        <span class="hint">页面生成完成后对话框将自动关闭</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dialog-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(15, 23, 42, 0.5);
  backdrop-filter: blur(4px);
}

.dialog-card {
  width: min(720px, 95vw);
  max-height: 90vh;
  overflow-y: auto;
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 24px 80px rgba(15, 23, 42, 0.25);
  padding: 28px 32px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.dialog-header strong {
  font-size: 18px;
}

.close-btn {
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #e3e8f0;
  border-radius: 8px;
  background: #fff;
  font-size: 16px;
  color: #5d6b82;
  cursor: pointer;
  padding: 0;
}

.close-btn:hover {
  background: #f1f5f9;
  color: #172033;
}

.progress-section {
  padding: 14px 16px;
  border-radius: 10px;
  background: #f7f9fc;
  border: 1px solid #e3e8f0;
}

.status-summary {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 8px;
  font-size: 14px;
}

.progress-track {
  overflow: hidden;
  height: 8px;
  border-radius: 999px;
  background: #e5eaf3;
}

.progress-fill {
  height: 100%;
  border-radius: 999px;
  background: #2864d8;
  transition: width 0.3s ease;
}

.status-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.status-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 12px;
  border: 1px solid #d9e0ea;
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  transition: border-color 0.15s;
}

.status-chip:hover {
  border-color: #2864d8;
}

.status-chip.active {
  border-color: #2864d8;
  background: #eaf1ff;
}

.status-chip.done {
  border-color: #c3ddfd;
}

.chip-idx {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 999px;
  background: #e5eaf3;
  font-size: 12px;
  font-weight: 700;
}

.status-chip.done .chip-idx {
  background: #c3ddfd;
}

.chip-title {
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chip-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  flex-shrink: 0;
}

.chip-dot.done {
  background: #22c55e;
}

.chip-dot.failed {
  background: #ef4444;
}

.chip-dot.pulse {
  background: #f59e0b;
  animation: pulse 1.2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.preview-section {
  border-top: 1px solid #e3e8f0;
  padding-top: 12px;
  max-height: 300px;
  overflow-y: auto;
}

.empty-preview {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100px;
  border: 2px dashed #e3e8f0;
  border-radius: 12px;
  padding: 16px;
  text-align: center;
}

.dialog-footer {
  text-align: center;
  padding-top: 4px;
}

.hint {
  color: #5d6b82;
  font-size: 13px;
}

.error {
  color: #d72d2d;
  font-size: 14px;
}
</style>
