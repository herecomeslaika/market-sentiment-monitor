<template>
  <div class="news-feed">
    <h2>新闻列表</h2>
    <div class="news-list">
      <div v-for="item in news" :key="item.id || item.title_hash" class="news-item" :class="sentimentClass(item)">
        <div class="news-header">
          <span class="news-source">{{ item.source }}</span>
          <span v-if="item.score !== undefined && item.score !== null" class="sentiment-badge" :class="sentimentClass(item)">
            {{ item.label }} {{ formatScore(item.score) }}
          </span>
        </div>
        <div class="news-title">{{ item.title }}</div>
        <div v-if="item.content_snippet" class="news-snippet">{{ item.content_snippet }}</div>
        <a v-if="item.url" :href="item.url" target="_blank" class="news-link">查看原文</a>
      </div>
    </div>
    <div v-if="!news.length" class="empty">暂无新闻数据</div>
  </div>
</template>

<script setup>
const props = defineProps({
  news: { type: Array, default: () => [] }
})

function sentimentClass(item) {
  if (item.score == null) return ''
  if (item.score < -0.3) return 'negative'
  if (item.score > 0.3) return 'positive'
  return 'neutral'
}

function formatScore(score) {
  return score.toFixed(2)
}
</script>

<style scoped>
.news-feed {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}
.news-feed h2 {
  margin: 0 0 12px;
  font-size: 18px;
}
.news-item {
  padding: 10px 12px;
  border-left: 3px solid #ddd;
  margin-bottom: 8px;
  border-radius: 4px;
  background: #fafafa;
}
.news-item.negative { border-left-color: #e74c3c; background: #fef5f5; }
.news-item.positive { border-left-color: #27ae60; background: #f5fef7; }
.news-item.neutral { border-left-color: #f39c12; background: #fefcf5; }
.news-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}
.news-source {
  font-size: 12px;
  color: #888;
}
.sentiment-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 600;
}
.sentiment-badge.negative { background: #fde8e8; color: #e74c3c; }
.sentiment-badge.positive { background: #e8f8ef; color: #27ae60; }
.sentiment-badge.neutral { background: #fef9e7; color: #f39c12; }
.news-title {
  font-size: 14px;
  line-height: 1.5;
  color: #333;
}
.news-snippet {
  font-size: 12px;
  color: #666;
  margin-top: 4px;
  line-height: 1.4;
}
.news-link {
  font-size: 12px;
  color: #3498db;
  text-decoration: none;
  margin-top: 4px;
  display: inline-block;
}
.empty {
  text-align: center;
  color: #999;
  padding: 24px;
}
</style>
