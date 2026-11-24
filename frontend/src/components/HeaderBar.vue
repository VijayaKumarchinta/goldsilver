<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  marketStatus: { type: String, required: true },
  lastPriceTime: { type: String, default: '' },
  feedStatus: { type: String, default: 'Market feed unavailable' },
  connected: { type: Boolean, default: true },
})

const emit = defineEmits(['toggle-theme'])

function getTheme() {
  return document.documentElement.getAttribute('data-theme') ||
    (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
}

const isDark = ref(getTheme() === 'dark')

const chipText = computed(() => props.feedStatus)
const chipDot = computed(() => props.connected ? 'green' : 'amber')

function toggleTheme() {
  emit('toggle-theme')
  isDark.value = !isDark.value
}
</script>

<template>
  <header class="header">
    <div class="header-inner">
      <a href="#" class="brand" aria-label="Bullion Desk India home">
        <span class="brand-mark">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="9"/>
            <path d="M12 3v18M3 12h18"/>
          </svg>
        </span>
        <span class="brand-text">
          Bullion Desk
          <small>India</small>
        </span>
      </a>

      <div class="header-right">
        <span class="header-market">
          {{ marketStatus }}
          <small v-if="lastPriceTime"> · Checked {{ lastPriceTime }}</small>
        </span>
        <span class="chip" :class="{ stale: !connected }">
          <span class="dot" :class="chipDot"></span>
          {{ chipText }}
        </span>
        <button
          class="icon-btn"
          type="button"
          @click="toggleTheme"
          :aria-label="isDark ? 'Switch to light mode' : 'Switch to dark mode'"
        >
          <svg v-if="isDark" viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
            <circle cx="12" cy="12" r="4"/>
            <path d="M12 2v2m0 16v2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M2 12h2m16 0h2M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42"/>
          </svg>
          <svg v-else viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
            <path d="M20.5 15.6A8.8 8.8 0 0 1 8.4 3.5 8.8 8.8 0 1 0 20.5 15.6Z"/>
          </svg>
          {{ isDark ? 'Light' : 'Dark' }}
        </button>
      </div>
    </div>
  </header>
</template>

<style scoped>
.header-market {
  white-space: normal;
  line-height: 1.35;
  text-align: right;
}

.header-market small {
  color: var(--mute);
  font-size: 10px;
  font-weight: 500;
}

.chip.stale {
  color: var(--ink-2);
}

@media (max-width: 640px) {
  .header-market {
    display: none;
  }
}
</style>
