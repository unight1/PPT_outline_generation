<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  NButton, NCard, NCollapse, NCollapseItem, NGi, NGrid, NInput,
  NInputNumber, NModal, NSelect, NSpace, NTag, NText, NRate,
} from 'naive-ui'
import type { EvalCase } from '../types/task'
import {
  listEvalCases, createEvalCase, deleteEvalCase, scoreEvalCase,
  getEvalStats,
} from '../api/evalApi'
import type { EvalStats } from '../api/evalApi'

const items = ref<EvalCase[]>([])
const stats = ref<EvalStats | null>(null)
const loading = ref(false)
const showCreate = ref(false)

const newItem = ref<Partial<EvalCase>>({
  topic: '',
  source_type: 'short_topic',
  expected_depth: 'L1',
  priority: 'medium',
  constraints: [],
})

const constraintsInput = ref('')

async function refresh() {
  loading.value = true
  try {
    items.value = await listEvalCases()
    stats.value = await getEvalStats()
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

async function handleCreate() {
  const constraints = constraintsInput.value
    .split('\n')
    .map(s => s.trim())
    .filter(Boolean)
  try {
    await createEvalCase({ ...newItem.value, constraints })
    showCreate.value = false
    newItem.value = { topic: '', source_type: 'short_topic', expected_depth: 'L1', priority: 'medium', constraints: [] }
    constraintsInput.value = ''
    void refresh()
  } catch (e) {
    console.error(e)
  }
}

async function handleDelete(evalId: string) {
  if (!confirm('确定删除？')) return
  await deleteEvalCase(evalId)
  void refresh()
}

async function handleScore(evalId: string, s: number) {
  await scoreEvalCase(evalId, { score: s })
  void refresh()
}

onMounted(() => { void refresh() })
</script>

<template>
  <div style="max-width:900px;margin:0 auto;padding:16px">
    <n-space justify="space-between" align="center" style="margin-bottom:16px">
      <n-text strong style="font-size:18px">评测数据集管理</n-text>
      <n-space>
        <n-button size="small" @click="showCreate = true">新建用例</n-button>
        <n-button size="small" @click="refresh" :loading="loading">刷新</n-button>
      </n-space>
    </n-space>

    <!-- Stats -->
    <n-grid v-if="stats" :cols="4" :x-gap="12" style="margin-bottom:16px">
      <n-gi><n-card size="small"><n-text depth="3">总数</n-text><br/><strong>{{ stats.total }}</strong></n-card></n-gi>
      <n-gi><n-card size="small"><n-text depth="3">已评分</n-text><br/><strong>{{ stats.scored }}</strong></n-card></n-gi>
      <n-gi><n-card size="small"><n-text depth="3">均分</n-text><br/><strong>{{ stats.average_score ?? '-' }}</strong></n-card></n-gi>
      <n-gi><n-card size="small"><n-text depth="3">高优先级</n-text><br/><strong>{{ stats.by_priority?.high ?? 0 }}</strong></n-card></n-gi>
    </n-grid>

    <!-- List -->
    <n-space vertical :size="12">
      <n-card v-for="item in items" :key="item.eval_id" size="small">
        <n-space vertical :size="8">
          <n-space justify="space-between" align="center">
            <n-space :size="8" align="center">
              <n-tag :bordered="false" :type="item.priority === 'high' ? 'error' : item.priority === 'medium' ? 'warning' : 'default'" size="small">
                {{ item.priority }}
              </n-tag>
              <n-tag :bordered="false" size="small">{{ item.status }}</n-tag>
              <n-text strong>{{ item.topic }}</n-text>
            </n-space>
            <n-button text type="error" size="small" @click="handleDelete(item.eval_id)">删除</n-button>
          </n-space>

          <n-space :size="6" align="center">
            <n-text depth="3" style="font-size:12px">
              深度: {{ item.expected_depth }} | 类型: {{ item.source_type }}
            </n-text>
            <n-text depth="3" style="font-size:12px" v-if="item.task_id">
              | 任务: {{ item.task_id?.slice(0, 8) }}...
            </n-text>
          </n-space>

          <n-space v-if="item.constraints?.length" :size="4">
            <n-tag v-for="c in item.constraints" :key="c" size="tiny" :bordered="false" type="info">{{ c }}</n-tag>
          </n-space>

          <n-space align="center" :size="10">
            <n-text depth="3" style="font-size:12px">评分: </n-text>
            <n-rate :value="item.score ?? 0" :count="5" size="small" @update:value="(v) => handleScore(item.eval_id, v)" />
            <n-text v-if="item.evaluator" depth="3" style="font-size:12px">| {{ item.evaluator }}</n-text>
            <n-text v-if="item.evidence_coverage != null" depth="3" style="font-size:12px">| 覆盖率: {{ item.evidence_coverage }}%</n-text>
          </n-space>

          <n-text v-if="item.notes" depth="3" style="font-size:12px">{{ item.notes }}</n-text>
        </n-space>
      </n-card>
    </n-space>

    <!-- Create Modal -->
    <n-modal v-model:show="showCreate" title="新建评测用例">
      <n-card style="width:500px">
        <n-space vertical :size="12">
          <n-input v-model:value="newItem.topic!" placeholder="PPT 主题 *" />
          <n-grid :cols="3" :x-gap="12">
            <n-gi>
              <n-select v-model:value="newItem.expected_depth!" :options="[
                { label: 'L0', value: 'L0' }, { label: 'L1', value: 'L1' }, { label: 'L2', value: 'L2' }
              ]" placeholder="检索深度" />
            </n-gi>
            <n-gi>
              <n-select v-model:value="newItem.priority!" :options="[
                { label: '高', value: 'high' }, { label: '中', value: 'medium' }, { label: '低', value: 'low' }
              ]" placeholder="优先级" />
            </n-gi>
            <n-gi>
              <n-select v-model:value="newItem.source_type!" :options="[
                { label: '短主题', value: 'short_topic' }, { label: '长文档', value: 'long_document' }
              ]" />
            </n-gi>
          </n-grid>
          <n-input
            v-model:value="constraintsInput"
            type="textarea"
            :rows="3"
            placeholder="约束条件，每行一条"
          />
          <n-button type="primary" block @click="handleCreate">创建</n-button>
        </n-space>
      </n-card>
    </n-modal>
  </div>
</template>

<style scoped>
.n-card {
  --n-padding-top: 10px;
  --n-padding-bottom: 10px;
}
</style>
