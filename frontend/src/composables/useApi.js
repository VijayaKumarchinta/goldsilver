import { ref, onMounted, onUnmounted, shallowRef, watch } from 'vue'
import { useSocket } from './useSocket'

// Single source of truth: the live MCX quote pushed by the backend over
// Socket.IO. There is no REST polling anywhere in the dashboard.
export function useApi() {
  const prices = shallowRef(null)
  const chart = shallowRef(null)
  const logsData = shallowRef(null)
  const purity = shallowRef(null)
  const loading = ref(false)
  const error = ref(null)
  const marketOpen = ref(false)
  const chartRange = ref('1D')
  const socket = useSocket()

  // connected defaults to false until the broker actually accepts the
  // WebSocket. The dashboard shows a loading state, not a false "live" flag.
  watch(
    () => socket.connected,
    (connected) => {
      if (connected && prices.value && !loading.value) {
        loadAll()
      }
    },
  )

  function refreshChart(range) {
    chartRange.value = range
    loadChart()
  }

  async function loadAll() {
    loading.value = true
    error.value = null
    try {
      const [latest, history, logs, purityData] = await Promise.all([
        socket.latest ? Promise.resolve(socket.latest) : Promise.reject(new Error('No live snapshot')),
        loadChart(),
        loadLogs(),
        loadPurity(),
      ])
      prices.value = latest
      marketOpen.value = latest?.market_open
      chart.value = history
      logsData.value = logs
      purity.value = purityData
    } catch (e) {
      const message = e?.message ?? 'Price feed unavailable'
      if (!socket.connected) {
        error.value = `Socket disconnected — ${message}`
      } else {
        error.value = message
      }
    } finally {
      loading.value = false
    }
  }

  async function loadChart() {
    try {
      const response = await fetch('/api/prices/chart/' + chartRange.value)
      if (!response.ok) {
        throw new Error('Chart refresh failed')
      }
      return response.json()
    } catch (e) {
      error.value = e?.message ?? 'Chart refresh failed'
      throw e
    }
  }

  async function loadLogs() {
    try {
      const response = await fetch('/api/logs')
      if (!response.ok) {
        throw new Error('Failed to load logs')
      }
      return response.json()
    } catch (e) {
      error.value = e?.message ?? 'Failed to load logs'
      throw e
    }
  }

  async function loadPurity() {
    try {
      const response = await fetch('/api/prices/purity')
      if (!response.ok) {
        throw new Error('Failed to load purity')
      }
      return response.json()
    } catch (e) {
      error.value = e?.message ?? 'Failed to load purity'
      throw e
    }
  }

  function reconnect() {
    if (socket.connected) {
      loadAll()
    }
  }

  onMounted(() => {
    socket.on('connect', reconnect)
  })

  onUnmounted(() => {
    socket.off('connect', reconnect)
  })

  return {
    prices,
    chart,
    logsData,
    purity,
    marketOpen,
    loading,
    error,
    chartRange,
    socket,
    connected: socket.connected,
    loadAll,
    refreshChart,
    reconnect,
  }
}
