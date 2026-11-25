import { ref, onMounted, onUnmounted, shallowRef, watch } from 'vue'
import { useSocket } from './useSocket'

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

  // Keep the live price stream alive and push live deltas back to the
  // server so the dashboard behaves as a two-way live stream.
  watch(
    () => socket.connected,
    (connected) => {
      if (connected && prices.value && !loading.value) {
        loadAll()
      }
    },
  )

  async function sendPriceDelta(client, snapshot) {
    const delta = {
      captured_at: snapshot.captured_at,
      market_open: snapshot.market_open,
      metals: {
        XAU: snapshot.metals.XAU,
        XAG: snapshot.metals.XAG,
      },
      fx: snapshot.fx,
      source: 'dashboard',
      client_id: client?.id || null,
    }
    return socket.sendPriceUpdate(delta)
  }

  // If the server acked a push, log it locally and keep the price stream
  // healthy by refreshing the chart on the next live quote.
  watch(
    () => socket.acked,
    (acked) => {
      if (acked && prices.value) {
        // no-op: the server ack is handled by the dashboard; the next
        // live price_update keeps the stream flowing.
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
    sendPriceDelta,
  }
}
