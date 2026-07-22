<script setup lang="ts">
import DefaultTheme from 'vitepress/theme'

const { Layout } = DefaultTheme
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
  padding: 12px 24px 24px;
}

@media (min-width: 640px) {
  .gemma-repo-wrapper {
    padding: 12px 48px 24px;
  }
}

@media (min-width: 960px) {
  .gemma-repo-wrapper {
    padding: 12px 64px 24px;
  }
}

.gemma-repo-container {
  margin: 0 auto;
  max-width: 1152px;
  width: 100%;
}
</style>
