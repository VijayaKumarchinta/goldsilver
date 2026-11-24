import { createApp } from 'vue'
import App from './App.vue'
import './style.css'

// Apply the saved theme before the first paint so the choice survives reloads.
try {
  const stored = localStorage.getItem('bullion-theme')
  if (stored === 'dark' || stored === 'light') {
    document.documentElement.setAttribute('data-theme', stored)
  }
} catch {
  // Storage can be blocked (private mode); the OS preference still applies.
}

createApp(App).mount('#app')
