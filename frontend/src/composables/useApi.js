import { ref } from 'vue'
import axios from 'axios'

// Same-origin by default: the Vite proxy in development, Flask (or a reverse proxy) in production.
// Set VITE_API_BASE only if the API lives on a different host.
const API_BASE = import.meta.env.VITE_API_BASE || '/api'

const api = axios.create({
  baseURL: API_BASE,
  timeout: 12000,
})

export function useApi() {
  const prices = ref(null)
  const chart = ref(null)
  const logsData = ref(null)
  const purity = ref(null)
  const loading = ref(false)
  const error = ref(null)
  const marketOpen = ref(false)
  const chartRange = ref('1D')
  let refreshTimer = null
  let autoRefreshCleanup = null

  async function loadAll() {
    loading.value = true
    error.value = null
    try {
      const results = await Promise.allSettled([
        api.get('/prices/latest').then((r) => {
          prices.value = r.data
          marketOpen.value = r.data.market_open
        }),
        api.get('/prices/chart/' + chartRange.value).then((r) => (chart.value = r.data)),
        api.get('/logs').then((r) => (logsData.value = r.data)),
        api.get('/prices/purity').then((r) => (purity.value = r.data)),
      ])
      const failed = results
        .filter((r) => r.status === 'rejected')
        .map((r) =>
          r.reason?.response?.data?.error
          ?? r.reason?.response?.data?.message
          ?? r.reason?.message
          ?? 'rejected'
        )
      if (results.every((r) => r.status === 'rejected')) {
        error.value = failed.length ? `Backend errors: ${failed.join('; ')}` : 'Backend unreachable'
      } else if (failed.length) {
        error.value = failed.length === 1
          ? failed[0]
          : `Some endpoints failed: ${failed.slice(0, 3).join('; ')}${failed.length > 3 ? '; ...' : ''}`
      } else if (prices.value?.gold?.live === false || prices.value?.silver?.live === false) {
        error.value = 'Live price feed unavailable; showing the last saved prices.'
      }
    } catch (e) {
      error.value = e?.message ?? 'Backend unreachable'
    } finally {
      loading.value = false
    }
  }

  function refreshWhenVisible() {
    if (document.visibilityState === 'visible' && !loading.value) {
      loadAll()
    }
  }

  function startAutoRefresh() {
    if (autoRefreshCleanup) autoRefreshCleanup()

    const updateRefreshTimer = () => {
      if (document.visibilityState === 'hidden') {
        if (refreshTimer) clearInterval(refreshTimer)
        refreshTimer = null
      } else if (!refreshTimer) {
        refreshTimer = setInterval(refreshWhenVisible, 5000)
        refreshWhenVisible()
      }
    }
    const cleanup = () => {
      if (refreshTimer) clearInterval(refreshTimer)
      refreshTimer = null
      document.removeEventListener('visibilitychange', updateRefreshTimer)
      window.removeEventListener('beforeunload', cleanup)
      autoRefreshCleanup = null
    }
    autoRefreshCleanup = cleanup
    document.addEventListener('visibilitychange', updateRefreshTimer)
    window.addEventListener('beforeunload', cleanup)
    updateRefreshTimer()
    return cleanup
  }

  async function refreshChart(range) {
    try {
      chartRange.value = range || '1D'
      const r = await api.get('/prices/chart/' + chartRange.value)
      chart.value = r.data
    } catch (e) {
      error.value = e?.response?.data?.error ?? e?.message ?? 'Chart refresh failed'
    }
  }

  return {
    prices,
    chart,
    logsData,
    purity,
    marketOpen,
    loading,
    error,
    loadAll,
    refreshChart,
    startAutoRefresh,
  }
}
