<script setup lang="ts">
import { computed, ref } from 'vue'

const props = withDefaults(
  defineProps<{
    contributors?: string[]
    body?: string
    author?: string
  }>(),
  {
    contributors: () => [],
    body: '',
    author: '',
  }
)

const nonExistent = ref<string[]>([])

const allContributors = computed(() => {
  let list: string[] = []

  if (props.body) {
    const matches = [...props.body.matchAll(/(?<=\(|(, ))@(.*?)(?=\)|(, ))/g)]
    list = matches.map(match => match[2])
  }

  if (props.contributors && props.contributors.length) {
    list = [...list, ...props.contributors]
  }

  if (props.author && !props.author.includes('[bot]')) {
    list = [props.author, ...list]
  }

  return [...new Set(list)]
    .filter(user => user && !user.includes('[bot]') && user !== 'github-actions' && !nonExistent.value.includes(user))
})

const listFormatter = new Intl.ListFormat('en', {
  style: 'long',
  type: 'conjunction',
})

const contributorsText = computed(() => {
  const users = allContributors.value
  if (users.length === 0) return ''
  if (users.length <= 3) return listFormatter.format(users)

  return listFormatter.format([
    ...users.slice(0, 2),
    `${users.length - 2} other contributors`,
  ])
})

function addToNonExistent(user: string) {
  if (!nonExistent.value.includes(user)) {
    nonExistent.value.push(user)
  }
}
</script>

<template>
  <div v-if="allContributors.length > 0" class="contributors">
    <h3>Contributors</h3>
    <ul class="avatars">
      <li v-for="contributor of allContributors" :key="contributor">
        <a
          :href="`https://github.com/${contributor}`"
          target="_blank"
          rel="noopener"
          :title="`${contributor} profile on GitHub`"
          :aria-label="`${contributor} profile on GitHub`"
        >
          <img
            :src="`https://github.com/${contributor}.png?size=32`"
            :alt="`@${contributor} profile picture`"
            loading="lazy"
            class="avatar"
            width="32"
            height="32"
            @error="addToNonExistent(contributor)"
          >
        </a>
      </li>
    </ul>
    <div class="names">
      {{ contributorsText }}
    </div>
  </div>
</template>

<style scoped>
:deep(.vp-doc) .contributors,
.contributors {
  margin-top: 20px !important;
  margin-bottom: 20px !important;
}

:deep(.vp-doc) .contributors h3,
.contributors h3 {
  font-size: 1.25rem !important;
  font-weight: 600 !important;
  line-height: 1.5 !important;
  color: var(--vp-c-text-1) !important;
  margin-top: 0 !important;
  margin-bottom: 4px !important;
}

:deep(.vp-doc) .contributors ul,
.contributors ul,
.contributors .avatars {
  display: flex !important;
  align-items: center !important;
  flex-wrap: wrap !important;
  gap: 0.5rem !important;
  list-style-type: none !important;
  padding-left: 0 !important;
  margin-top: 4px !important;
  margin-bottom: 4px !important;
}

:deep(.vp-doc) .contributors ul li,
.contributors ul li {
  line-height: 0 !important;
  padding: 0 !important;
  margin: 0 !important;
}

:deep(.vp-doc) .contributors ul li::before,
.contributors ul li::before {
  content: none !important;
  display: none !important;
}

.contributors .avatar {
  width: 32px !important;
  height: 32px !important;
  border-radius: 50% !important;
  box-shadow: var(--vp-shadow-1) !important;
  border: 1px solid var(--vp-c-divider) !important;
  transition: transform 0.2s ease, border-color 0.2s ease !important;
  background: var(--vp-c-bg-alt) !important;
}

.contributors .avatar:hover {
  transform: scale(1.1) !important;
  border-color: var(--vp-c-brand-1) !important;
}

.contributors .names {
  font-size: 0.875rem !important;
  color: var(--vp-c-text-2) !important;
  line-height: 1.4 !important;
  margin-top: 2px !important;
}
</style>
