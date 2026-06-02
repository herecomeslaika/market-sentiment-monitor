<template>
  <div class="intent-search">
    <input
      v-model="intent"
      placeholder="输入研究意图，如：降息对银行股的影响、AI芯片竞争格局..."
      @keyup.enter="generate"
      :disabled="loading"
    />
    <button @click="generate" :disabled="loading || !intent.trim()">
      {{ loading ? '生成中...' : '生成研报' }}
    </button>
  </div>
  <div v-if="error" class="intent-error">{{ error }}</div>
  <div v-if="result && !error" class="intent-result">
    <div class="result-header">
      <span class="result-id">{{ result.report_id }}</span>
      <span class="result-count">基于 {{ result.news_count }} 条新闻</span>
      <span class="result-time">{{ result.created_at }}</span>
      <button class="btn-view" @click="$emit('viewReport', result)">查看完整报告</button>
    </div>
    <div class="result-keywords">
      <span v-for="kw in result.keywords" :key="kw" class="kw-tag">{{ kw }}</span>
    </div>
    <div class="result-preview">{{ preview }}</div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const emit = defineEmits(['viewReport'])

const intent = ref('')
const loading = ref(false)
const error = ref('')
const result = ref(null)

const preview = computed(() => {
  if (!result.value?.deep_analysis) return ''
  const text = result.value.deep_analysis
  return text.length > 200 ? text.slice(0, 200) + '...' : text
})

async function generate() {
  if (!intent.value.trim()) return
  loading.value = true
  error.value = ''
  result.value = null
  try {
    const res = await fetch('/reports/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ intent: intent.value }),
    })
    const data = await res.json()
    if (data.error) {
      error.value = data.error
      return
    }
    result.value = data
    intent.value = ''
  } catch (e) {
    error.value = '生成失败: ' + e.message
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.intent-search {
  display: flex;
  gap: 8px;
}
.intent-search input {
  flex: 1;
  padding: 10px 14px;
  border: 2px solid #ddd;
  border-radius: 8px;
  font-size: 15px;
  transition: border-color 0.2s;
}
.intent-search input:focus {
  outline: none;
  border-color: #3498db;
  box-shadow: 0 0 0 3px rgba(52,152,219,0.1);
}
.intent-search button {
  padding: 10px 24px;
  border: none;
  border-radius: 8px;
  background: #3498db;
  color: #fff;
  font-size: 15px;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.2s;
}
.intent-search button:hover:not(:disabled) { background: #2980b9; }
.intent-search button:disabled { opacity: 0.5; cursor: default; }
.intent-error {
  margin-top: 8px;
  color: #e74c3c;
  font-size: 13px;
}
.intent-result {
  margin-top: 10px;
  background: #f0f8ff;
  border: 1px solid #d4e6f1;
  border-radius: 8px;
  padding: 12px;
}
.result-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}
.result-id {
  font-size: 11px;
  color: #888;
  background: #eee;
  padding: 2px 6px;
  border-radius: 4px;
}
.result-count {
  font-size: 12px;
  color: #666;
}
.result-time {
  font-size: 11px;
  color: #999;
}
.btn-view {
  margin-left: auto;
  padding: 4px 12px;
  border: 1px solid #3498db;
  border-radius: 4px;
  background: transparent;
  color: #3498db;
  font-size: 12px;
  cursor: pointer;
}
.btn-view:hover { background: #3498db; color: #fff; }
.result-keywords { margin-bottom: 6px; }
.kw-tag {
  font-size: 11px;
  background: #e8f4fd;
  color: #2980b9;
  padding: 1px 6px;
  border-radius: 8px;
  margin-right: 4px;
}
.result-preview {
  font-size: 13px;
  color: #444;
  line-height: 1.5;
}
</style>