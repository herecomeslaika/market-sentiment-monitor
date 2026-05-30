<template>
  <div class="subscription-manager">
    <h3>订阅管理</h3>
    <div class="form">
      <input v-model="keywords" placeholder="关键词 (逗号分隔)" class="input kw-input" />
      <input v-model.number="threshold" type="number" step="0.1" min="-1" max="0" class="input thresh-input" />
      <button @click="handleSubscribe" class="btn" :disabled="!keywords.trim()">订阅</button>
    </div>
    <div v-if="subscription" class="current-sub">
      <div class="sub-info">
        <span v-for="kw in subscription.keywords" :key="kw" class="kw-tag">{{ kw }}</span>
        <span class="thresh">阈值: {{ subscription.threshold }}</span>
      </div>
      <button @click="handleUnsubscribe" class="btn btn-danger">取消订阅</button>
    </div>
    <div v-else class="no-sub">暂无订阅</div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  subscription: { type: Object, default: null }
})

const emit = defineEmits(['subscribe', 'unsubscribe'])

const keywords = ref('')
const threshold = ref(-0.5)

function handleSubscribe() {
  const kw = keywords.value.split(',').map(k => k.trim()).filter(k => k)
  if (!kw.length) return
  emit('subscribe', { keywords: kw, threshold: threshold.value })
  keywords.value = ''
}

function handleUnsubscribe() {
  emit('unsubscribe')
}
</script>

<style scoped>
.subscription-manager {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}
.subscription-manager h3 {
  margin: 0 0 12px;
  font-size: 16px;
}
.form {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.input {
  padding: 6px 10px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 13px;
}
.kw-input { flex: 1; min-width: 0; }
.thresh-input { width: 70px; }
.btn {
  padding: 6px 14px;
  border: none;
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
  background: #3498db;
  color: #fff;
}
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-danger { background: #e74c3c; }
.current-sub {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px;
  background: #f9f9f9;
  border-radius: 4px;
}
.sub-info {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}
.kw-tag {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
  background: #e8f4fd;
  color: #2980b9;
}
.thresh {
  font-size: 12px;
  color: #666;
  margin-left: 4px;
}
.no-sub {
  text-align: center;
  color: #999;
  font-size: 13px;
  padding: 8px;
}
</style>
