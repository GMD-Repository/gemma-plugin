<script setup lang="ts">
import { ref } from 'vue'

const repoUrl = 'https://gmd-repository.github.io/gemma-plugin/gemma.xml'
const copied = ref(false)

async function copyUrl() {
  try {
    await navigator.clipboard.writeText(repoUrl)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch {
    const textarea = document.createElement('textarea')
    textarea.value = repoUrl
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  }
}
</script>

<template>
  <div class="qgis-repo-card">
    <div class="card-header">
      <div class="header-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>
      </div>
      <div class="header-text">
        <h3 class="title">QGIS Plugin Repository URL</h3>
        <p class="subtitle">Copy the repository URL below to add it in QGIS Plugin Manager (Plugins → Manage and Install Plugins → Settings → Add...)</p>
      </div>
    </div>

    <div class="code-block-container">
      <pre class="code-content"><code>{{ repoUrl }}</code></pre>
      <button
        class="copy-btn"
        :class="{ copied }"
        @click="copyUrl"
        :title="copied ? 'Copied to clipboard' : 'Copy URL'"
        :aria-label="copied ? 'Copied to clipboard' : 'Copy URL'"
      >
        <span v-if="copied" class="copy-status">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
          Copied
        </span>
        <span v-else class="copy-status">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
          </svg>
          Copy
        </span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.qgis-repo-card {
  background-color: var(--vp-c-bg-soft);
  border: 1px solid var(--vp-c-divider);
  border-radius: 12px;
  padding: 16px 20px;
  margin: 0;
  transition: border-color 0.25s, background-color 0.25s;
}

.qgis-repo-card:hover {
  border-color: var(--vp-c-brand-1);
}

.card-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.header-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background-color: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
  flex-shrink: 0;
}

.header-text {
  flex: 1;
}

.title {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--vp-c-text-1);
  line-height: 1.3;
}

.subtitle {
  margin: 2px 0 0;
  font-size: 0.8125rem;
  color: var(--vp-c-text-2);
  line-height: 1.4;
}

.code-block-container {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background-color: var(--vp-c-bg);
  border: 1px solid var(--vp-c-divider);
  border-radius: 8px;
  padding: 8px 12px 8px 16px;
  gap: 12px;
  transition: border-color 0.25s;
}

.code-block-container:hover {
  border-color: var(--vp-c-brand-1);
}

.code-content {
  margin: 0;
  padding: 0;
  overflow-x: auto;
  font-family: var(--vp-font-family-mono);
  font-size: 0.85rem;
  line-height: 1.5;
  flex: 1;
  min-width: 0;
}

.code-content code {
  color: var(--vp-c-brand-1);
  font-weight: 500;
  white-space: nowrap;
}

.copy-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 6px 12px;
  border-radius: 6px;
  border: 1px solid var(--vp-c-divider);
  background-color: var(--vp-c-bg-soft);
  color: var(--vp-c-text-2);
  font-size: 0.75rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.copy-status {
  display: flex;
  align-items: center;
  gap: 5px;
}

.copy-btn:hover {
  background-color: var(--vp-c-bg-alt);
  color: var(--vp-c-text-1);
  border-color: var(--vp-c-brand-1);
}

.copy-btn.copied {
  color: var(--vp-c-green-1);
  border-color: var(--vp-c-green-1);
  background-color: var(--vp-c-green-soft);
}
</style>
