<script setup lang="ts">
import { ref, computed } from 'vue'
import type { Outline, Slide, Task } from '../types/task'
import SlidePanel from './SlidePanel.vue'

const props = defineProps<{
  outline: Outline
  taskProgress: Task['progress']
  regeneratingSlideId: string | null
  saving: boolean
  saveMessage: string
}>()

const emit = defineEmits<{
  (e: 'update:outline', outline: Outline): void
  (e: 'save'): void
  (e: 'restart'): void
  (e: 'regenerate', slideId: string): void
  (e: 'copy-markdown'): void
  (e: 'download-markdown'): void
  (e: 'update:slide', slide: Slide): void
}>()

const currentIndex = ref(0)

const totalSlides = computed(() => props.outline.slides.length)

function goTo(index: number) {
  if (index >= 0 && index < totalSlides.value) {
    currentIndex.value = index
  }
}

function goPrev() {
  goTo(currentIndex.value - 1)
}

function goNext() {
  goTo(currentIndex.value + 1)
}

const currentSlide = computed(() => props.outline.slides[currentIndex.value] ?? null)

const isRegenerating = computed(() =>
  currentSlide.value ? props.regeneratingSlideId === currentSlide.value.slide_id : false,
)
</script>

<template>
  <div class="deck-layout">
    <!-- Left sidebar: page list -->
    <aside class="deck-sidebar">
      <div class="sidebar-header">
        <strong>页面列表</strong>
        <span class="hint">{{ totalSlides }} 页</span>
      </div>

      <div class="sidebar-pages">
        <button
          v-for="(slide, idx) in outline.slides"
          :key="slide.slide_id"
          :class="['page-thumb', { active: idx === currentIndex }]"
          @click="goTo(idx)"
        >
          <span class="thumb-idx">{{ idx + 1 }}</span>
          <span class="thumb-title">{{ slide.title || slide.slide_id }}</span>
        </button>
      </div>
    </aside>

    <!-- Main: current slide display -->
    <div class="deck-main">
      <div class="deck-nav">
        <button class="secondary small" :disabled="currentIndex === 0" @click="goPrev">
          ← 上一页
        </button>
        <span class="nav-pos">{{ currentIndex + 1 }} / {{ totalSlides }}</span>
        <button
          class="secondary small"
          :disabled="currentIndex >= totalSlides - 1"
          @click="goNext"
        >
          下一页 →
        </button>
      </div>

      <!-- Regeneration progress -->
      <div
        v-if="isRegenerating && taskProgress"
        class="progress-box"
      >
        <strong>{{ taskProgress.message || '正在重新生成该页...' }}</strong>
        <div
          v-if="typeof taskProgress.percent === 'number'"
          class="progress-track"
        >
          <div
            class="progress-fill"
            :style="{ width: `${taskProgress.percent}%` }"
          />
        </div>
      </div>

      <SlidePanel
        v-if="currentSlide"
        :slide="currentSlide"
        :index="currentIndex"
        :total="totalSlides"
        :editable="true"
        :regenerating="isRegenerating"
        :evidence-catalog="outline.evidence_catalog"
        @update:slide="(s) => emit('update:slide', s)"
        @regenerate="(id) => emit('regenerate', id)"
      />
    </div>
  </div>
</template>

<style scoped>
.deck-layout {
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: 24px;
  min-height: 400px;
}

.deck-sidebar {
  border-right: 1px solid #e3e8f0;
  padding-right: 16px;
}

.sidebar-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 12px;
}

.sidebar-pages {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.page-thumb {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid #e3e8f0;
  border-radius: 8px;
  background: #fbfcff;
  text-align: left;
  cursor: pointer;
  font: inherit;
  color: inherit;
  transition: border-color 0.15s, background 0.15s;
}

.page-thumb:hover {
  border-color: #2864d8;
}

.page-thumb.active {
  border-color: #2864d8;
  background: #eaf1ff;
  font-weight: 700;
}

.thumb-idx {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 999px;
  background: #e5eaf3;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}

.page-thumb.active .thumb-idx {
  background: #2864d8;
  color: #fff;
}

.thumb-title {
  font-size: 13px;
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.deck-main {
  min-width: 0;
  overflow-y: auto;
  max-height: calc(100vh - 200px);
  padding-right: 12px;
}

.deck-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
  padding: 1px 0 3px;
  border-bottom: 1px solid #f0f2f5;
  position: sticky;
  top: 0;
  background: #fff;
  z-index: 3;
}

.nav-pos {
  font-size: 14px;
  font-weight: 600;
  color: #5d6b82;
}

.progress-box {
  margin-bottom: 16px;
  padding: 12px;
  border-radius: 10px;
  background: #f7f9fc;
  border: 1px solid #e3e8f0;
}

.progress-track {
  overflow: hidden;
  height: 6px;
  margin-top: 8px;
  border-radius: 999px;
  background: #e5eaf3;
}

.progress-fill {
  height: 100%;
  border-radius: 999px;
  background: #2864d8;
  transition: width 0.3s ease;
}

.hint {
  color: #5d6b82;
  font-size: 13px;
}

button.small {
  padding: 4px 14px;
  font-size: 13px;
  white-space: nowrap;
  line-height: 1.35;
}

@media (max-width: 720px) {
  .deck-layout {
    grid-template-columns: 1fr;
  }

  .deck-sidebar {
    border-right: none;
    border-bottom: 1px solid #e3e8f0;
    padding-right: 0;
    padding-bottom: 12px;
  }

  .sidebar-pages {
    flex-direction: row;
    flex-wrap: wrap;
  }

  .page-thumb {
    flex-shrink: 0;
  }
}
</style>
