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
  <div class="card">
    <div class="card-header">
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--vp-c-brand-1)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>
      <h3>QGIS Plugin Repository</h3>
    </div>
    <p class="desc">Copy the repository URL below and add it to QGIS Plugin Manager to install and automatically receive plugin updates.</p>

    <div class="code-block-wrapper">
      <button
        class="copy-btn"
        :class="{ copied }"
        @click="copyUrl"
        :title="copied ? 'Copied' : 'Copy Code'"
        :aria-label="copied ? 'Copied' : 'Copy Code'"
      >
        <svg v-if="!copied" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
        </svg>
        <svg v-else xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="20 6 9 17 4 12"/>
        </svg>
      </button>
      <pre class="code-content"><code>{{ repoUrl }}</code></pre>
    </div>
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
.desc {
  margin: 0 0 16px;
  font-size: 0.875rem;
  color: var(--vp-c-text-2);
  line-height: 1.6;
}

/* Code block matching VitePress code block style */
.code-block-wrapper {
  position: relative;
  background: var(--vp-c-bg-alt);
  border-radius: 8px;
  overflow: hidden;
}
.code-content {
  margin: 0;
  padding: 16px 52px 16px 20px;
  overflow-x: auto;
  font-family: var(--vp-font-family-mono);
  font-size: 0.875rem;
  line-height: 1.5;
}
.code-content code {
  color: var(--vp-c-text-1);
  white-space: nowrap;
}

/* Copy button icon: hidden by default (opacity: 0), appears on hover */
.copy-btn {
  position: absolute;
  top: 10px;
  right: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 4px;
  border: 1px solid var(--vp-c-divider);
  background: var(--vp-c-bg-alt);
  color: var(--vp-c-text-2);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.25s ease, background-color 0.25s ease, color 0.25s ease, border-color 0.25s ease;
  z-index: 3;
}

/* Show copy button icon on hover matching Getting Started page code blocks */
.code-block-wrapper:hover .copy-btn,
.copy-btn:focus,
.copy-btn.copied {
  opacity: 1;
}

.copy-btn:hover {
  background: var(--vp-c-bg);
  color: var(--vp-c-text-1);
  border-color: var(--vp-c-text-2);
}

.copy-btn.copied {
  color: var(--vp-c-green-1);
  border-color: var(--vp-c-green-1);
  background: var(--vp-c-green-soft);
}
</style>
