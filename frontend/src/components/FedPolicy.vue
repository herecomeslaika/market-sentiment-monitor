<template>
  <div class="fed-policy" :class="{ expanded: expanded }">
    <div class="fed-header" @click="toggleExpand">
      <div class="fed-header-left">
        <span class="expand-icon">{{ expanded ? '▼' : '▶' }}</span>
        <span class="fed-title">Fed Policy</span>
        <template v-if="policy && !expanded">
          <span class="header-badge" :class="rateTrendClass">{{ policy.rate_trend }}</span>
          <span class="header-badge" :class="stanceClass">{{ policy.policy_stance }}</span>
        </template>
      </div>
      <div class="fed-header-right">
        <button class="btn-icon" @click.stop="refresh" :disabled="loading" title="Refresh">
          {{ loading ? '...' : '↻' }}
        </button>
      </div>
    </div>

    <div v-if="error && expanded" class="fed-error">{{ error }}</div>

    <div v-if="expanded && policy" class="fed-content">
      <div class="fed-cards">
        <div class="fed-card">
          <span class="card-label">Rate Trend</span>
          <span class="card-value" :class="rateTrendClass">{{ policy.rate_trend || '--' }}</span>
        </div>
        <div class="fed-card">
          <span class="card-label">Stance</span>
          <span class="card-value" :class="stanceClass">{{ policy.policy_stance || '--' }}</span>
        </div>
        <div class="fed-card">
          <span class="card-label">QE/QT</span>
          <span class="card-value">{{ policy.qt_qe_status || '--' }}</span>
        </div>
      </div>

      <div class="fed-summary">
        <p>{{ policy.summary || 'No summary available' }}</p>
        <div v-if="policy.outlook" class="fed-outlook">
          Outlook: {{ policy.outlook }}
        </div>
        <div v-if="policy.rate_level" class="fed-rate-level">
          {{ policy.rate_level }}
        </div>
      </div>

      <div v-if="policy.key_events?.length" class="fed-events">
        <ul>
          <li v-for="(event, i) in policy.key_events" :key="i">{{ event }}</li>
        </ul>
      </div>

      <div class="fed-news">
        <span class="news-label">Related News ({{ policy.news_count || 0 }})</span>
        <div v-if="newsLoading" class="news-loading">...</div>
        <ul v-else-if="news.length">
          <li v-for="item in news" :key="item.id || item.title">
            <a v-if="item.url" :href="item.url" target="_blank" rel="noopener">
              <span class="news-source">{{ item.source }}</span>
              {{ item.title }}
            </a>
            <span v-else>
              <span class="news-source">{{ item.source }}</span>
              {{ item.title }}
            </span>
          </li>
        </ul>
        <p v-else class="no-news">No related news</p>
      </div>

      <div class="fed-footer">
        <button @click="generateReport">Generate Full Report</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'

const emit = defineEmits(['generateReport'])

const policy = ref(null)
const news = ref([])
const loading = ref(false)
const newsLoading = ref(false)
const error = ref('')
const expanded = ref(false)

const rateTrendClass = computed(() => {
  const t = policy.value?.rate_trend || ''
  if (t.includes('cutting') || t.includes('降息')) return 'trend-cut'
  if (t.includes('hiking') || t.includes('加息')) return 'trend-hike'
  return ''
})

const stanceClass = computed(() => {
  const s = policy.value?.policy_stance || ''
  if (s.includes('dovish') || s.includes('鸽派')) return 'stance-dovish'
  if (s.includes('hawkish') || s.includes('鹰派')) return 'stance-hawkish'
  return ''
})

function toggleExpand() {
  expanded.value = !expanded.value
  if (expanded.value && !policy.value) {
    fetchPolicy()
    fetchNews()
  }
}

async function fetchPolicy(forceRefresh = false) {
  loading.value = true
  error.value = ''
  try {
    const url = forceRefresh ? '/fed-policy?refresh=true' : '/fed-policy'
    const res = await fetch(url)
    if (!res.ok) throw new Error('request failed')
    policy.value = await res.json()
  } catch (e) {
    error.value = 'Failed: ' + e.message
  } finally {
    loading.value = false
  }
}

async function fetchNews() {
  newsLoading.value = true
  try {
    const res = await fetch('/fed-policy/news?limit=10')
    if (res.ok) news.value = await res.json()
  } catch (e) {
    console.error('Fed news fetch error:', e)
  } finally {
    newsLoading.value = false
  }
}

async function refresh() {
  expanded.value = true
  await fetchPolicy(true)
  await fetchNews()
}

function generateReport() {
  emit('generateReport', '美联储货币政策现状及未来展望')
}

onMounted(() => {
  fetchPolicy()
})
</script>

<style scoped>
.fed-policy {
  background: #fff;
  border-radius: 6px;
  border: 1px solid #e0e0e0;
  transition: all 0.2s;
}
.fed-policy:not(.expanded) {
  padding: 0;
}
.fed-policy.expanded {
  padding: 12px;
}
.fed-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  cursor: pointer;
  user-select: none;
}
.fed-policy.expanded .fed-header {
  padding: 0 0 10px 0;
}
.fed-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.expand-icon {
  font-size: 11px;
  color: #888;
}
.fed-title {
  font-size: 14px;
  font-weight: 600;
}
.header-badge {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 4px;
  background: #f0f0f0;
  font-weight: 500;
}
.trend-cut { background: #e8f8ef; color: #27ae60; }
.trend-hike { background: #fdf2f2; color: #e74c3c; }
.stance-dovish { background: #e8f4fd; color: #3498db; }
.stance-hawkish { background: #fef5e7; color: #e67e22; }
.fed-header-right {
  display: flex;
  gap: 6px;
}
.btn-icon {
  padding: 4px 10px;
  border: 1px solid #ddd;
  border-radius: 4px;
  background: #f8f9fa;
  font-size: 14px;
  cursor: pointer;
  line-height: 1;
}
.btn-icon:hover:not(:disabled) { background: #e9ecef; }
.btn-icon:disabled { opacity: 0.4; cursor: default; }
.fed-error {
  color: #e74c3c;
  font-size: 13px;
  padding: 6px 10px;
  background: #fdf2f2;
  border-radius: 4px;
}
.fed-cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin-bottom: 10px;
}
.fed-card {
  background: #f8f9fa;
  border-radius: 4px;
  padding: 8px 6px;
  text-align: center;
}
.card-label {
  display: block;
  font-size: 11px;
  color: #888;
  margin-bottom: 2px;
}
.card-value {
  font-size: 13px;
  font-weight: 600;
}
.fed-summary {
  background: #f0f8ff;
  border-radius: 4px;
  padding: 10px;
  margin-bottom: 8px;
}
.fed-summary p {
  font-size: 13px;
  line-height: 1.5;
  margin: 0;
  color: #333;
}
.fed-outlook, .fed-rate-level {
  margin-top: 6px;
  font-size: 12px;
  color: #555;
}
.fed-events {
  margin-bottom: 8px;
}
.fed-events ul {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
}
.fed-events li {
  margin-bottom: 3px;
}
.fed-news {
  border-top: 1px solid #eee;
  padding-top: 8px;
}
.news-label {
  font-size: 12px;
  color: #888;
  display: block;
  margin-bottom: 4px;
}
.fed-news ul {
  margin: 0;
  padding: 0;
  list-style: none;
}
.fed-news li {
  padding: 4px 0;
  border-bottom: 1px solid #f5f5f5;
  font-size: 12px;
}
.fed-news li:last-child { border-bottom: none; }
.fed-news a {
  color: #333;
  text-decoration: none;
}
.fed-news a:hover { color: #3498db; }
.news-source {
  color: #888;
  font-size: 11px;
  margin-right: 4px;
}
.news-loading, .no-news {
  color: #888;
  font-size: 12px;
}
.fed-footer {
  margin-top: 8px;
  text-align: right;
}
.fed-footer button {
  padding: 4px 12px;
  border: 1px solid #3498db;
  border-radius: 4px;
  background: transparent;
  color: #3498db;
  font-size: 12px;
  cursor: pointer;
}
.fed-footer button:hover {
  background: #3498db;
  color: #fff;
}
</style>