<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { withBase } from 'vitepress'

interface LatestRelease {
  version: string
  tag: string
  releaseDate: string
  downloadUrl: string
  releaseUrl: string
  changelogUrl: string
}

const data = ref<LatestRelease | null>(null)
const loading = ref(true)

onMounted(async () => {
  try {
    const res = await fetch(withBase('/latest.json'))
    data.value = await res.json()
  } catch (e) {
    console.warn('Failed to load latest.json:', e)
  } finally {
    loading.value = false
  }
})

function formatDate(dateStr: string): string {
  const d = new Date(dateStr + 'T00:00:00')
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}
</script>

<template>
  <div class="card">
    <div class="card-header">
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--vp-c-brand-1)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
      <h3>Latest Release</h3>
      <span v-if="data" class="badge">v{{ data.version }}</span>
    </div>

    <template v-if="loading">
      <div class="skeleton" style="height: 16px; width: 50%; margin-bottom: 12px;"></div>
      <div class="skeleton" style="height: 36px; width: 100%;"></div>
    </template>

    <template v-else-if="data">
      <p class="date">Released {{ formatDate(data.releaseDate) }}</p>
      <div class="actions">
        <a :href="data.downloadUrl" class="vp-btn brand">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          Download
        </a>
        <a :href="withBase('/changelog/')" class="vp-btn alt">Changelog →</a>
        <a :href="data.releaseUrl" target="_blank" rel="noopener" class="vp-btn alt">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4"/><path d="M9 18c-4.51 2-5-2-7-2"/></svg>
          GitHub
        </a>
      </div>
    </template>

    <template v-else>
      <p class="date">
        Unable to load release info. <a href="https://github.com/GMD-Repository/gemma-plugin/releases/latest" target="_blank">View on GitHub →</a>
      </p>
    </template>
  </div>
</template>

<style scoped>
.card {
  background: var(--vp-c-bg-soft);
  border: 1px solid var(--vp-c-divider);
  border-radius: 12px;
  padding: 24px;
  transition: border-color 0.25s;
}
.card:hover {
  border-color: var(--vp-c-brand-1);
}
.card-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.card-header h3 {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--vp-c-text-1);
}
.badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 100px;
  font-size: 0.75rem;
  font-weight: 700;
  background: var(--vp-c-brand-1);
  color: var(--vp-c-white);
}
.date {
  margin: 0 0 14px;
  font-size: 0.8125rem;
  color: var(--vp-c-text-3);
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.vp-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 16px;
  border-radius: 8px;
  font-size: 0.8125rem;
  font-weight: 600;
  text-decoration: none;
  transition: all 0.25s;
  white-space: nowrap;
}
.vp-btn.brand {
  background: var(--vp-c-brand-1);
  color: var(--vp-c-white);
}
.vp-btn.brand:hover {
  background: var(--vp-c-brand-2);
}
.vp-btn.alt {
  background: var(--vp-c-bg);
  color: var(--vp-c-brand-1);
  border: 1px solid var(--vp-c-divider);
}
.vp-btn.alt:hover {
  border-color: var(--vp-c-brand-1);
}
.skeleton {
  background: var(--vp-c-bg-alt);
  border-radius: 6px;
  animation: pulse 1.5s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
</style>
