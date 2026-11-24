import { ref } from 'vue'

const STORAGE_KEY = 'bullion-theme'

function systemPrefersDark() {
  return typeof window !== 'undefined' && window.matchMedia
    ? window.matchMedia('(prefers-color-scheme: dark)').matches
    : false
}

function storedTheme() {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return value === 'dark' || value === 'light' ? value : null
  } catch {
    return null
  }
}

/**
 * The <html data-theme> attribute is the only source of truth. It is written
 * before the app mounts (see main.js), so the button and the page can never
 * disagree about the current theme.
 */
export function resolveTheme() {
  const attr = document.documentElement.getAttribute('data-theme')
  if (attr === 'dark' || attr === 'light') return attr
  return storedTheme() || (systemPrefersDark() ? 'dark' : 'light')
}

const theme = ref(resolveTheme())

function apply(next, persist) {
  theme.value = next
  document.documentElement.setAttribute('data-theme', next)
  if (!persist) return
  try {
    localStorage.setItem(STORAGE_KEY, next)
  } catch {
    // Storage can be blocked (private mode); the theme still applies for this session.
  }
}

export function useTheme() {
  return {
    theme,
    isDark: () => theme.value === 'dark',
    toggle() {
      apply(theme.value === 'dark' ? 'light' : 'dark', true)
    },
  }
}
