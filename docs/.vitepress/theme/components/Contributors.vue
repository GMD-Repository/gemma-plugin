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
    <h3>Contributors</h3>
    <ul class="avatars-list">
      <li v-for="user in cleanContributors" :key="user">
        <a
          :href="`https://github.com/${user}`"
          :title="`${user} profile on GitHub`"
          :aria-label="`${user} profile on GitHub`"
          target="_blank"
          rel="noopener"
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
  margin-top: 14px;
  margin-bottom: 14px;
}
.contributors h3 {
  font-size: 1rem;
  font-weight: 600;
  color: var(--vp-c-text-1);
  margin-top: 0;
  margin-bottom: 8px;

}
.avatars-list {
  display: flex;
  align-items: center;
  gap: 8px;
  list-style: none;
  padding: 0;
  margin: 0 0 6px;
}
.avatars-list li {
  line-height: 0;
  padding: 0;
  margin: 0;
}
.avatars-list li::before {
  content: none !important;
}
.avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 1px solid var(--vp-c-divider);
  transition: transform 0.2s, border-color 0.2s;
  background: var(--vp-c-bg-alt);
}
.avatar:hover {
  transform: scale(1.1);
  border-color: var(--vp-c-brand-1);
}
.names {
  font-size: 0.85rem;
  color: var(--vp-c-text-2);
  line-height: 1.4;
}
</style>
