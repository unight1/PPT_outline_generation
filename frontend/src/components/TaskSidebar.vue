<script setup lang="ts">
defineProps<{
  showHistory?: boolean
}>()

defineEmits<{
  (e: 'new-task'): void
}>()
</script>

<template>
  <aside class="sidebar">
    <!-- Placeholder: task history -->
    <div v-if="showHistory" class="section">
      <strong class="section-title">最近任务</strong>
      <p class="hint empty-text">对接中 — 任务列表将在接入后端后显示</p>
    </div>

    <!-- Placeholder: document analysis status -->
    <div class="section">
      <strong class="section-title">高级检索</strong>
      <label class="disabled-row">
        <input type="checkbox" disabled />
        优先使用我的文档
      </label>
      <label class="disabled-row">
        来源质量过滤
        <select disabled>
          <option>默认</option>
        </select>
      </label>
      <p class="hint empty-text">对接中 — 上传文档与检索策略即将支持</p>
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

.disabled-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 8px 0;
  font-size: 13px;
  color: #94a3b8;
  cursor: not-allowed;
}

.disabled-row select,
.disabled-row input {
  opacity: 0.5;
  pointer-events: none;
}

.empty-text {
  font-size: 12px;
  font-style: italic;
}

.hint {
  color: #5d6b82;
  font-size: 13px;
}
</style>
