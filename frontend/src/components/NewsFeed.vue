<template>
  <div class="news-feed">
    <div v-if="!news.length" class="empty">暂无新闻</div>
    <div v-for="n in news" :key="n.id || n.title_hash" class="news-item">
      <div class="news-header">
        <span class="source-badge">{{ n.source }}</span>
        <span class="time">{{ formatTime(n.created_at) }}</span>
      </div>
      <div class="title">{{ n.title }}</div>
      <div v-if="n.content_snippet" class="snippet">{{ n.content_snippet?.slice(0, 100) }}</div>
    </div>
  </div>
</template>

<script setup>
defineProps({ news: { type: Array, default: () => [] } })

function formatTime(t) {
  if (!t) return ''
  return new Date(t).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}
</script>

<style scoped>
.news-feed { max-height: 400px; overflow-y: auto; }
.news-item { padding: 10px 12px; border-radius: 8px; margin-bottom: 6px; background: #0f172a; }
.news-header { display: flex; justify-content: space-between; margin-bottom: 4px; }
.source-badge { font-size: 11px; padding: 2px 8px; border-radius: 4px; background: #1e3a5f; color: #93c5fd; }
.time { font-size: 11px; color: #64748b; }
.title { font-size: 13px; font-weight: 500; }
.snippet { font-size: 12px; color: #94a3b8; margin-top: 4px; }
.empty { color: #64748b; font-size: 13px; text-align: center; padding: 40px 0; }
</style>
