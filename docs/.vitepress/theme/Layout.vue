<script setup lang="ts">
import DefaultTheme from 'vitepress/theme'
import { onMounted } from 'vue'
import { withBase } from 'vitepress'

const { Layout } = DefaultTheme

onMounted(async () => {
  try {
    const res = await fetch(withBase('/latest.json'))
    if (res.ok) {
      const data = await res.json()
      if (data.downloadUrl) {
        // Dynamic auto-update for both hero and top nav bar Download links
        const downloadLinks = document.querySelectorAll<HTMLAnchorElement>('a')
        downloadLinks.forEach(link => {
          const text = link.textContent?.trim().toLowerCase()
          if (text === 'download' || text === 'direct download') {
            link.href = data.downloadUrl
          }
        })
      }
    }
  } catch (e) {
    console.warn('Could not update download URL from latest.json:', e)
  }
})
</script>

<template>
  <Layout>
    <template #home-hero-after>
      <div class="gemma-repo-wrapper">
        <div class="gemma-repo-container">
          <QGISRepositoryCard />
        </div>
      </div>
    </template>
  </Layout>
</template>

<style scoped>
.gemma-repo-wrapper {
  position: relative;
  padding: 0 24px 24px;
  margin-top: -16px;
}

@media (min-width: 640px) {
  .gemma-repo-wrapper {
    padding: 0 48px 24px;
    margin-top: -24px;
  }
}

@media (min-width: 960px) {
  .gemma-repo-wrapper {
    padding: 0 64px 24px;
    margin-top: -32px;
  }
}

.gemma-repo-container {
  margin: 0 auto;
  max-width: 1152px;
  width: 100%;
}
</style>
