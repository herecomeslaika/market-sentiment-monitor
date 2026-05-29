<template>
  <div class="sub-manager">
    <div class="form">
      <input v-model="userId" placeholder="用户ID" class="input" />
      <input v-model="keywords" placeholder="关键词 (逗号分隔)" class="input" />
      <input v-model.number="threshold" type="number" step="0.1" min="-1" max="1" placeholder="阈值" class="input small" />
      <button @click="subscribe" class="btn primary">订阅</button>
    </div>
    <div v-if="subs.length" class="sub-list">
      <div v-for="s in subs" :key="s.user_id" class="sub-item">
        <span class="user">{{ s.user_id }}</span>
        <span class="kws">{{ s.keywords?.join(', ') }}</span>
        <span class="thresh">{{ s.threshold }}</span>
        <button @click="unsubscribe(s.user_id)" class="btn danger small">删除</button>
      </div>
    </div>
    <p v-else class="empty">暂无订阅</p>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useApi } from '../composables/useApi.js'

const api = useApi()
const userId = ref('')
const keywords = ref('')
const threshold = ref(-0.5)
const subs = ref([])

async function fetchSubs() {
  try { subs.value = await api.get('/subscriptions') } catch {}
}

async function subscribe() {
  if (!userId.value || !keywords.value) return
  const kwList = keywords.value.split(/[,，]/).map(k => k.trim()).filter(Boolean)
  await api.post('/subscriptions', { user_id: userId.value, keywords: kwList, threshold: threshold.value })
  keywords.value = ''
  await fetchSubs()
}

async function unsubscribe(uid) {
  await api.del(`/subscriptions/${uid}`)
  await fetchSubs()
}

onMounted(fetchSubs)
</script>

<style scoped>
.form { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.input { background: #0f172a; border: 1px solid #334155; border-radius: 6px; padding: 6px 10px; color: #e2e8f0; font-size: 13px; }
.input.small { width: 70px; }
.btn { padding: 6px 14px; border-radius: 6px; border: none; cursor: pointer; font-size: 13px; font-weight: 500; }
.btn.primary { background: #3b82f6; color: white; }
.btn.danger { background: #7f1d1d; color: #fca5a5; }
.btn.small { padding: 3px 10px; font-size: 11px; }
.sub-list { }
.sub-item { display: flex; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px solid #1e293b; font-size: 13px; }
.user { color: #93c5fd; font-weight: 500; }
.kws { flex: 1; color: #cbd5e1; }
.thresh { color: #94a3b8; font-size: 12px; }
.empty { color: #64748b; font-size: 13px; text-align: center; padding: 20px 0; }
</style>
