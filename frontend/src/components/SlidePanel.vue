<script setup lang="ts">
import { computed, ref } from 'vue'
import { NModal } from 'naive-ui'
import type { Evidence, Slide } from '../types/task'

const props = defineProps<{
  slide: Slide
  index: number
  total: number
  editable?: boolean
  regenerating?: boolean
  evidenceCatalog?: Evidence[]
}>()

const emit = defineEmits<{
  (e: 'update:slide', slide: Slide): void
  (e: 'regenerate', slideId: string): void
}>()

const showEvidence = ref(false)

const slideEvidence = computed(() => {
  if (!props.evidenceCatalog) return []
  const refIds = new Set(props.slide.bullets.flatMap((b) => b.evidence_ids))
  return props.evidenceCatalog.filter((ev) => refIds.has(ev.evidence_id))
})

function emitUpdate(patch: Partial<Slide>) {
  emit('update:slide', { ...props.slide, ...patch } as Slide)
}

function updateBulletText(bulletId: string, text: string) {
  emit('update:slide', {
    ...props.slide,
    bullets: props.slide.bullets.map((b) =>
      b.bullet_id === bulletId ? { ...b, text } : b,
    ),
  })
}
</script>

<template>
  <article class="slide-panel">
    <!-- Header -->
    <div class="panel-header">
      <span class="page-badge">{{ index + 1 }} / {{ total }}</span>
      <input v-if="editable" class="title-inline" :value="slide.title"
        @input="emitUpdate({ title: ($event.target as HTMLInputElement).value })" />
      <strong v-else class="page-title-label">{{ slide.title || '(未命名)' }}</strong>
      <button v-if="editable" class="secondary small" :disabled="regenerating" type="button"
        @click="$emit('regenerate', slide.slide_id)">
        {{ regenerating ? '重生成中...' : '重新生成' }}
      </button>
    </div>

    <!-- Key message -->
    <div class="field-row">
      <label class="field-label">核心结论</label>
      <input v-if="editable" class="field-input key-input" :value="slide.key_message ?? ''" placeholder="听众能记住的一句话..."
        @input="emitUpdate({ key_message: ($event.target as HTMLInputElement).value })" />
      <p v-else class="key-text">{{ slide.key_message || '—' }}</p>
    </div>

    <!-- Bullets -->
    <div class="field-row bullets-area">
      <label class="field-label">要点</label>
      <ul class="bullet-edit-list">
        <li v-for="bullet in slide.bullets" :key="bullet.bullet_id" class="bullet-edit-item">
          <textarea v-if="editable" class="field-input bullet-ta" :value="bullet.text" rows="2"
            @input="updateBulletText(bullet.bullet_id, ($event.target as HTMLTextAreaElement).value)" />
          <span v-else>{{ bullet.text }}</span>
          <button v-if="bullet.evidence_ids.length" class="ev-chip" type="button" title="点击查看证据详情"
            @click="showEvidence = !showEvidence">
            {{ bullet.evidence_ids.join(', ') }}
          </button>
        </li>
      </ul>
    </div>

    <!-- Secondary fields: 2-column -->
    <div class="field-row two-col">
      <div class="field-col">
        <label class="field-label">讲者备注</label>
        <textarea v-if="editable" class="field-input" :value="slide.speaker_notes ?? ''" rows="3"
          @input="emitUpdate({ speaker_notes: ($event.target as HTMLTextAreaElement).value })" />
        <p v-else class="hint-text">{{ slide.speaker_notes || '—' }}</p>
      </div>
      <div class="field-col">
        <label class="field-label">配图建议</label>
        <input v-if="editable" class="field-input" :value="slide.visual_suggestion ?? ''" placeholder="柱状图 / 流程图..."
          @input="emitUpdate({ visual_suggestion: ($event.target as HTMLInputElement).value })" />
        <p v-else class="hint-text">{{ slide.visual_suggestion || '—' }}</p>
      </div>
    </div>

    <div class="field-row">
      <label class="field-label">听众行动建议</label>
      <input v-if="editable" class="field-input" :value="slide.takeaway ?? ''" placeholder="会后行动建议..."
        @input="emitUpdate({ takeaway: ($event.target as HTMLInputElement).value })" />
      <p v-else class="hint-text">{{ slide.takeaway || '—' }}</p>
    </div>

    <!-- Evidence button -->
    <div v-if="slideEvidence.length" class="evidence-btn-row">
      <button class="ev-toggle" type="button" @click="showEvidence = true">
        证据详情 · {{ slideEvidence.length }} 条
      </button>
    </div>

    <n-modal v-model:show="showEvidence" preset="card" title="本页证据详情" style="width:min(600px,95vw)"
      :mask-closable="true">
      <div class="ev-body">
        <article v-for="ev in slideEvidence" :key="ev.evidence_id" class="ev-card">
          <div class="ev-meta">
            <strong>{{ ev.evidence_id }}</strong>
            <span class="ev-source">{{ ev.source_id }}</span>
          </div>
          <p class="ev-snippet">{{ ev.snippet }}</p>
          <small class="ev-detail">{{ ev.locator }} · score: {{ ev.score?.toFixed(2) ?? '—' }}</small>
        </article>
      </div>
    </n-modal>
  </article>
</template>

<style scoped>
.slide-panel {
  padding: 0;
}

/* Header */
.panel-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
  padding: 1px 0 3px;
  border-bottom: 1px solid #f0f2f5;
  position: sticky;
  top: 0;
  background: #fff;
  z-index: 2;
}

.page-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 40px;
  padding: 2px 6px;
  border-radius: 999px;
  background: #eaf1ff;
  color: #1f4eb0;
  font-size: 11px;
  font-weight: 700;
  white-space: nowrap;
}

.page-title-label {
  flex: 1;
  font-size: 14px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.title-inline {
  flex: 1;
  padding: 3px 8px;
  border: 1px solid #cbd5e1;
  border-radius: 5px;
  font: inherit;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.35;
}

/* Fields */
.field-row {
  margin-bottom: 12px;
}

.field-label {
  display: block;
  font-size: 12px;
  font-weight: 700;
  color: #5d6b82;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 4px;
}

.field-input {
  box-sizing: border-box;
  width: 100%;
  padding: 9px 12px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  font: inherit;
  font-size: 15px;
  line-height: 1.5;
}

.field-input:focus {
  outline: none;
  border-color: #2864d8;
  box-shadow: 0 0 0 2px rgba(40, 100, 216, 0.1);
}

textarea.field-input {
  resize: vertical;
  min-height: 42px;
}

.key-input {
  font-weight: 600;
  font-size: 16px;
  color: #1f4eb0;
}

.key-text {
  font-size: 15px;
  font-weight: 600;
  color: #1f4eb0;
  margin: 2px 0;
}

/* Bullets */
.bullets-area {
  margin-bottom: 6px;
}

.bullet-edit-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.bullet-edit-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 6px;
}

.bullet-edit-item::before {
  content: '•';
  color: #2864d8;
  font-weight: 700;
  flex-shrink: 0;
  padding-top: 10px;
  font-size: 16px;
}

.bullet-ta {
  flex: 1;
  min-height: 38px;
  font-size: 14px;
  padding: 7px 10px;
}

.ev-chip {
  display: inline-flex;
  align-items: center;
  padding: 2px 7px;
  border: 1px solid #c3ddfd;
  border-radius: 999px;
  background: #eaf1ff;
  color: #1f4eb0;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
  margin-top: 4px;
}

.ev-chip:hover {
  background: #d0e4ff;
}

/* Two column */
.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.field-col {
  min-width: 0;
}

/* Evidence button */
.evidence-btn-row {
  margin-top: 8px;
  border-top: 1px solid #e3e8f0;
  padding-top: 8px;
}

.ev-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  border: none;
  background: none;
  color: #5d6b82;
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  width: 100%;
  text-align: left;
}

.ev-toggle:hover {
  color: #2864d8;
}

.ev-count {
  font-size: 11px;
  color: #94a3b8;
  font-weight: 400;
}

.ev-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
  max-height: 240px;
  overflow-y: auto;
}

.ev-card {
  padding: 10px 12px;
  border: 1px solid #e3e8f0;
  border-radius: 8px;
  background: #f7f9fc;
  font-size: 13px;
}

.ev-meta {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 4px;
}

.ev-source {
  font-size: 11px;
  color: #5d6b82;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 200px;
}

.ev-snippet {
  margin: 4px 0;
  line-height: 1.5;
  color: #333;
}

.ev-detail {
  color: #94a3b8;
}

/* ── Misc ── */
.hint-text {
  font-size: 13px;
  color: #5d6b82;
  margin: 2px 0;
}

button.small {
  padding: 4px 14px;
  font-size: 13px;
  white-space: nowrap;
  flex-shrink: 0;
  line-height: 1.35;
}
</style>
