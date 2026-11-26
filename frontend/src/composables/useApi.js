import { ref, onMounted, onUnmounted, shallowRef, watch } from 'vue'
import { useSocket } from './useSocket'

const apiBase = (import.meta.env.VITE_API_BASE || '/api').replace(/\/+$/, '')

function toNumber(value) {
  if (value === null || value === undefined || value === '') return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

// The REST endpoint reports `gold`/`silver` with a per-10g close, while the
// socket broadcast reports `metals.XAU`/`metals.XAG` with a per-gram rate.
// Normalise both into the single quote shape the dashboard renders.
function normalizeQuote(quote) {
  if (!quote) return null
  const perGram = toNumber(quote.inr_per_gram)
  const close = toNumber(quote.close)
    ?? toNumber(quote.inr_per_10g)
    ?? (perGram === null ? null : perGram * 10)
  return {
    ...quote,
    inr_per_gram: perGram,
    close,
    open: toNumber(quote.open) ?? toNumber(quote.open_per_10g),
    live: Boolean(quote.live),
  }
}

function normalizeSnapshot(data) {
  if (!data || typeof data !== 'object') return null
  const metals = data.metals && typeof data.metals === 'object'
    ? data.metals
    : { XAU: data.gold, XAG: data.silver }
  return {
    ...data,
    metals: {
      XAU: normalizeQuote(metals.XAU),
      XAG: normalizeQuote(metals.XAG),
    },
    fx: data.fx || {},
    feed: data.feed || null,
  }
}

async function getJson(path, label) {
  const response = await fetch(apiBase + path)
  if (!response.ok) {
    throw new Error(`${label} failed (${response.status})`)
  }
  return response.json()
}

export function useApi() {
  const prices = shallowRef(null)
  const chart = shallowRef(null)
  const logsData = shallowRef(null)
  const purity = shallowRef(null)
  const loading = ref(false)
  const error = ref(null)
  const marketOpen = ref(false)
  const chartRange = ref('1D')
  const { latest, connected } = useSocket()

  // Live updates win over the initial REST snapshot. When a broadcast omits
  // the feed health block, keep the one we already have.
  watch(
    latest,
    (snapshot) => {
      if (!snapshot) return
      const normalized = normalizeSnapshot(snapshot)
      if (!normalized) return
      prices.value = { ...normalized, feed: normalized.feed ?? prices.value?.feed ?? null }
      marketOpen.value = Boolean(normalized.market_open)
      error.value = null
    },
    { immediate: true },
  )

  watch(connected, (isConnected) => {
    if (isConnected) loadAll()
  })

  async function loadChart() {
    try {
      return await getJson(`/prices/chart/${chartRange.value}`, 'Chart refresh')
    } catch (e) {
      error.value = e?.message ?? 'Chart refresh failed'
      throw e
    }
  }

  async function loadLogs() {
    try {
      return await getJson('/logs', 'Delivery log load')
    } catch (e) {
      error.value = e?.message ?? 'Failed to load logs'
      throw e
    }
  }

  async function loadPurity() {
    try {
      return await getJson('/prices/purity', 'Purity load')
    } catch (e) {
      error.value = e?.message ?? 'Failed to load purity'
      throw e
    }
  }

  async function loadAll() {
    loading.value = true
    error.value = null
    const [latestResult, chartResult, logsResult, purityResult] = await Promise.allSettled([
      getJson('/prices/latest', 'Price feed'),
      loadChart(),
      loadLogs(),
      loadPurity(),
    ])

    // Do not overwrite a newer socket snapshot with the REST response.
    if (latestResult.status === 'fulfilled' && !latest.value) {
      const snapshot = normalizeSnapshot(latestResult.value)
      if (snapshot) {
        prices.value = snapshot
        marketOpen.value = Boolean(snapshot.market_open)
      }
    }
    if (chartResult.status === 'fulfilled') chart.value = chartResult.value
    if (logsResult.status === 'fulfilled') logsData.value = logsResult.value
    if (purityResult.status === 'fulfilled') purity.value = purityResult.value

    const failure = [latestResult, chartResult, logsResult, purityResult]
      .find((result) => result.status === 'rejected')
    if (failure) {
      const message = failure.reason?.message || 'Some dashboard data could not be loaded'
      error.value = connected.value ? message : `Socket disconnected - ${message}`
    }
    loading.value = false
  }

  // The backend records a chart snapshot every 5 minutes, so refetch the
  // selected range on the same cadence while the page stays open.
  async function refreshChartData() {
    try {
      chart.value = await loadChart()
    } catch {
      // loadChart() already surfaced the failure through `error`; treat this
      // refresh as best-effort so callers never see a rejection.
    }
  }

  // The socket snapshot has no feed-health block, so the stale banner would
  // otherwise only refresh on mount/reconnect. Poll the REST endpoint that
  // exposes it on the same 5-minute tick.

  // When the page comes back after a reload, the banner must not outlive a
  // successful reload. readReload() re-checks every source the first time
  // loadAll() runs (mount, reconnect) and resets `error` on success.
  async function readReload() {
    const [latestResult] = await Promise.allSettled([getJson('/prices/latest', 'Reload price feed')])
    if (latestResult.status === 'fulfilled') {
      const snapshot = normalizeSnapshot(latestResult.value)
      if (snapshot) {
        prices.value = snapshot
        marketOpen.value = Boolean(snapshot.market_open)
        error.value = null
      }
    }
  }

  async function refreshFeedHealth() {
    try {
      const snapshot = normalizeSnapshot(await getJson('/prices/latest', 'Feed health'))
      if (!snapshot) return
      if (prices.value) {
        prices.value = { ...prices.value, feed: snapshot.feed ?? prices.value.feed ?? null }
      } else {
        prices.value = snapshot
      }
      marketOpen.value = Boolean(snapshot.market_open)
    } catch {
      // Keep the previous banner; the next tick retries.
    }
  }

  function refreshChart(range) {
    chartRange.value = range
    return refreshChartData()
  }

  // Called by loadAll() on mount and by App.vue when the user retries a
  // failed data load. After a full reload both paths re-read every source;
  // only then does the stale banner receive the all-clear.
  async function retryLoad() {
    await loadAll()
    if (!error.value) {
      readReload()
    }
  }

  let chartTimer = null

  onMounted(async () => {
    await retryLoad()
    chartTimer = setInterval(() => {
      refreshChartData()
      refreshFeedHealth()
    }, 5 * 60 * 1000)
  })

  onUnmounted(() => {
    if (chartTimer) clearInterval(chartTimer)
    chartTimer = null
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
    connected,
    loadAll,
    refreshChart,
  }
}
