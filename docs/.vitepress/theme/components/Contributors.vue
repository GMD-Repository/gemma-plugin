<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  contributors: string[]
}>()

const cleanContributors = computed(() => {
  if (!props.contributors) return []
  return Array.from(new Set(props.contributors.filter(user => user && !user.includes('[bot]'))))
})

const formattedNames = computed(() => {
  const list = cleanContributors.value
  if (!list || list.length === 0) return ''
  if (list.length === 1) return list[0]
  if (list.length === 2) return `${list[0]} and ${list[1]}`
  const firstTwo = list.slice(0, 2).join(', ')
  const remaining = list.length - 2
  return `${firstTwo}, and ${remaining} other contributor${remaining > 1 ? 's' : ''}`
})
</script>

<template>
  <div class="contributors" v-if="cleanContributors.length">
    <h3 class="title">Contributors</h3>
    <ul class="avatars-list">
      <li v-for="user in cleanContributors" :key="user">
        <a
          :href="`https://github.com/${user}`"
          :title="`${user} profile on GitHub`"
          :aria-label="`${user} profile on GitHub`"
          target="_blank"
          rel="noopener"
          class="avatar-link"
        >
          <img
            :src="`https://github.com/${user}.png?size=64`"
            :alt="`@${user}`"
            loading="lazy"
            class="avatar"
            width="32"
            height="32"
          />
        </a>
      </li>
    </ul>
    <div class="names">
      {{ formattedNames }}
    </div>
  </div>
</template>

<style scoped>
.contributors {
  margin-top: 20px;
  margin-bottom: 20px;
}

.contributors .title {
  font-size: 1.25rem;
  font-weight: 600;
  line-height: 1.6;
  color: var(--vp-c-text-1);
  margin: 0;
  letter-spacing: -0.02em;
}

.avatars-list {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  list-style: none;
  padding: 0;
  margin-top: 8px;
  margin-bottom: 8px;
}

.avatars-list li {
  line-height: 1;
  padding: 0;
  margin: 0;
}

.avatars-list li::before {
  content: none !important;
}

.avatar-link {
  display: inline-block;
  line-height: 0;
}

.avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.15);
  transition: transform 0.2s ease, border-color 0.2s ease;
  background: var(--vp-c-bg-alt);
}

.avatar:hover {
  transform: scale(1.1);
  border-color: var(--vp-c-brand-1);
}

.names {
  font-size: 0.9rem;
  color: var(--vp-c-text-2);
  line-height: 1.3;
  margin-top: 0;
}
</style>
