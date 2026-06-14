<script setup lang="ts">
import { ref } from 'vue'
import { NButton, NCard, NInput, NSpace, NText } from 'naive-ui'
import { login } from '../api'

const username = ref('')
const password = ref('')
const errorMsg = ref('')
const loading = ref(false)

const emit = defineEmits<{
  loggedIn: [username: string]
}>()

async function handleLogin() {
  if (!username.value.trim() || !password.value.trim()) {
    errorMsg.value = '请输入用户名和密码'
    return
  }
  loading.value = true
  errorMsg.value = ''
  try {
    const result = await login({
      username: username.value.trim(),
      password: password.value,
    })
    localStorage.setItem('access_token', result.access_token)
    localStorage.setItem('username', result.username)
    localStorage.setItem('role', result.role)
    emit('loggedIn', result.username)
  } catch (e: unknown) {
    errorMsg.value = e instanceof Error ? e.message : '登录失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-shell">
    <n-card title="PPT Outline 登录" style="width: 360px">
      <n-space vertical :size="14">
        <n-input v-model:value="username" placeholder="用户名" size="large" @keyup.enter="handleLogin" />
        <n-input v-model:value="password" type="password" placeholder="密码" size="large" @keyup.enter="handleLogin" />
        <n-button type="primary" block :loading="loading" @click="handleLogin">
          登录
        </n-button>
        <n-text v-if="errorMsg" type="error" depth="2" style="text-align:center;display:block">
          {{ errorMsg }}
        </n-text>
        <n-text depth="3" style="text-align:center;display:block;font-size:12px">
          预置账号：admin / admin123 或 user / user123
        </n-text>
      </n-space>
    </n-card>
  </div>
</template>

<style scoped>
.login-shell {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100vh;
  background: #f0f2f5;
}
</style>
