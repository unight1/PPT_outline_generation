<script setup lang="ts">
import { onMounted, ref } from 'vue'

const health = ref<string>('加载中…')
const ready = ref<string>('')

async function load() {
  try {
    const h = await fetch('/api/health')
    const hj = await h.json()
    health.value = JSON.stringify(hj)

    const r = await fetch('/api/health/ready')
    const rj = await r.json()
    ready.value = JSON.stringify(rj, null, 2)
  } catch (e) {
    health.value = `请求失败（请先启动后端）：${e}`
    ready.value = ''
  }
}

onMounted(load)
</script>

<template>
  <main class="page">
    <h1>PPT 大纲智能生成</h1>
    <p class="hint">前端开发服务器通过 Vite 把 <code>/api</code> 代理到后端 <code>:8000</code>。</p>

    <section>
      <h2>GET /api/health</h2>
      <pre>{{ health }}</pre>
    </section>

    <section>
      <h2>GET /api/health/ready</h2>
      <pre>{{ ready || '（与 MySQL / Redis 配置相关，见 .env）' }}</pre>
    </section>

    <button type="button" @click="load">重新检测</button>
  </main>
</template>

<style scoped>
.page {
  font-family: system-ui, sans-serif;
  max-width: 48rem;
  margin: 2rem auto;
  padding: 0 1rem;
}
.hint {
  color: #555;
  font-size: 0.95rem;
}
section {
  margin-top: 1.5rem;
}
pre {
  background: #f4f4f5;
  padding: 1rem;
  border-radius: 8px;
  overflow: auto;
}
button {
  margin-top: 1rem;
  padding: 0.5rem 1rem;
  cursor: pointer;
}
</style>
