import { createApp } from 'vue'
import App from './App.vue'
import './style.css'
import { resolveTheme } from './composables/useTheme'

// Resolve the theme before the first paint so a saved choice survives reloads
// and a system dark-mode preference is honoured from the start.
document.documentElement.setAttribute('data-theme', resolveTheme())

createApp(App).mount('#app')
