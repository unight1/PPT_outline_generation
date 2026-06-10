<script setup lang="ts">
import { ref, computed } from 'vue'
import type { Chapter, Outline, Slide, Task } from '../types/task'
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
  (e: 'regenerate', slideId: string, userInstruction?: string): void
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

const chapterGroups = computed(() => {
  const chapters = props.outline.chapters ?? []
  if (!chapters.length) {
    const grouped = new Map<string, string[]>()
    for (const slide of props.outline.slides) {
      if (!slide.chapter_id) continue
      grouped.set(slide.chapter_id, [...(grouped.get(slide.chapter_id) ?? []), slide.slide_id])
    }
    if (grouped.size > 0) {
      return Array.from(grouped, ([chapter_id, slide_ids]) => {
        const firstTitle = props.outline.slides.find((slide) => slide.slide_id === slide_ids[0])?.title
        return {
          chapter_id,
          title: firstTitle ? `章节：${firstTitle}` : chapter_id,
          slide_ids,
        }
      }) satisfies Chapter[]
    }
    return [
      {
        chapter_id: 'all',
        title: '全部页面',
        slide_ids: props.outline.slides.map((slide) => slide.slide_id),
      },
    ] satisfies Chapter[]
  }
  return chapters.map((chapter) => {
    if (chapter.title && !/^ch\d+$/i.test(chapter.title)) return chapter
    const firstTitle = props.outline.slides.find((slide) => slide.slide_id === chapter.slide_ids[0])?.title
    return {
      ...chapter,
      title: firstTitle ? `章节：${firstTitle}` : chapter.chapter_id,
    }
  })
})

const slideIndexById = computed(() => {
  const map = new Map<string, number>()
  props.outline.slides.forEach((slide, index) => map.set(slide.slide_id, index))
  return map
})

const lowConfidenceCount = computed(() => {
  const slide = currentSlide.value
  if (!slide) return 0
  return slide.bullets.filter((bullet) => !bullet.evidence_ids?.length).length
})

const currentEvidenceCount = computed(() => {
  const slideId = currentSlide.value?.slide_id
  if (!slideId) return 0
  const trace = props.outline.page_evidence_map?.find((item) => item.slide_id === slideId)
  return trace?.evidence_trace?.length ?? 0
})

const currentEvidenceTrace = computed(() => {
  const slideId = currentSlide.value?.slide_id
  if (!slideId) return []
  return props.outline.page_evidence_map?.find((item) => item.slide_id === slideId)?.evidence_trace ?? []
})
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
        <section
          v-for="chapter in chapterGroups"
          :key="chapter.chapter_id"
          class="chapter-group"
        >
          <strong class="chapter-title">{{ chapter.title }}</strong>
          <button
            v-for="slideId in chapter.slide_ids"
            :key="slideId"
            :class="['page-thumb', { active: slideIndexById.get(slideId) === currentIndex }]"
            @click="goTo(slideIndexById.get(slideId) ?? -1)"
          >
            <span class="thumb-idx">{{ (slideIndexById.get(slideId) ?? 0) + 1 }}</span>
            <span class="thumb-title">
              {{ outline.slides[slideIndexById.get(slideId) ?? 0]?.title || slideId }}
            </span>
          </button>
        </section>
      </div>
    </aside>

    <!-- Main: current slide display -->
    <div class="deck-main">
      <div class="deck-nav">
        <button class="secondary small" :disabled="currentIndex === 0" @click="goPrev">
          ← 上一页
        </button>
        <span class="nav-pos">
          {{ currentIndex + 1 }} / {{ totalSlides }}
          <small v-if="currentEvidenceCount" class="nav-evidence">证据 {{ currentEvidenceCount }} 条</small>
          <small v-if="lowConfidenceCount" class="nav-warning">低可信 {{ lowConfidenceCount }} 条</small>
        </span>
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
        @regenerate="(id, instruction) => emit('regenerate', id, instruction)"
      />

      <section v-if="currentEvidenceTrace.length" class="page-evidence">
        <strong>本页证据追踪</strong>
        <article
          v-for="item in currentEvidenceTrace"
          :key="String(item.evidence_id)"
          class="trace-card"
        >
          <div class="trace-meta">
            <span>{{ item.evidence_id }}</span>
            <small>支撑要点：{{ Array.isArray(item.bullet_ids) ? item.bullet_ids.join(', ') : '—' }}</small>
          </div>
          <p>{{ item.snippet }}</p>
          <small>{{ item.source_id }} · {{ item.locator }}</small>
        </article>
      </section>
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
  gap: 12px;
}

.chapter-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.chapter-title {
  padding: 2px 2px 0;
  color: #5d6b82;
  font-size: 12px;
  font-weight: 700;
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
  padding: 0 12px 72px 0;
  box-sizing: border-box;
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
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: #5d6b82;
}

.nav-evidence,
.nav-warning {
  padding: 2px 7px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
}

.nav-evidence {
  background: #eaf1ff;
  color: #1f4eb0;
}

.nav-warning {
  background: #fff7ed;
  color: #c2410c;
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

.page-evidence {
  margin-top: 14px;
  padding: 12px;
  border: 1px solid #e3e8f0;
  border-radius: 10px;
  background: #f7f9fc;
}

.trace-card {
  margin-top: 8px;
  padding: 9px 10px;
  border-radius: 8px;
  background: #fff;
  border: 1px solid #e5eaf3;
  font-size: 13px;
}

.trace-card p {
  margin: 6px 0;
  line-height: 1.5;
  color: #334155;
}

.trace-meta {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  color: #1f4eb0;
  font-weight: 700;
}

.trace-card small {
  color: #5d6b82;
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
