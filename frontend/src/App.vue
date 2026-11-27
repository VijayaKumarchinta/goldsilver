<script setup>
import { computed, ref, watch } from 'vue'
import HeaderBar from './components/HeaderBar.vue'
import NotificationLogs from './components/NotificationLogs.vue'
import PriceChart from './components/PriceChart.vue'
import PurityTable from './components/PurityTable.vue'
import { useApi } from './composables/useApi'
import { money } from './utils/format.js'

const { prices, chart, logsData, purity, marketOpen, loading, error, refreshChart, retryLoad } = useApi()
const chartRange = ref('1D')

function parseDate(value) {
  if (!value) return null
  const date = new Date(String(value).replace(' ', 'T'))
  return Number.isNaN(date.getTime()) ? null : date
}

function formatDateTime(value) {
  const date = parseDate(value)
  if (!date) return '-'
  return date.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Kolkata',
    hour12: true,
  }) + ' IST'
}

function chartValue(value) {
  if (value === null || value === undefined || value === '') return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

const chartRows = computed(() => {
  if (!Array.isArray(chart.value?.labels)) return []
  return chart.value.labels.map((label, index) => ({
    key: `${label}-${index}`,
    label: formatDateTime(label),
    gold: chartValue(chart.value.gold?.[index]),
    silver: chartValue(chart.value.silver?.[index]),
  })).filter((row) => row.gold !== null || row.silver !== null)
})

const latestSavedQuote = computed(() => chartRows.value[chartRows.value.length - 1] || null)
const liveData = computed(() => prices.value?.metals ?? null)
const gold = computed(() => liveData.value?.XAU ?? null)
const silver = computed(() => liveData.value?.XAG ?? null)
const feedLive = computed(() => Boolean(gold.value?.live && silver.value?.live))
const feedStatus = computed(() => {
  if (!prices.value) return loading.value ? 'Connecting to price feed' : 'Price feed unavailable'
  return feedLive.value ? 'Live prices' : 'Saved prices'
})
const feedAlert = computed(() => {
  const feed = prices.value?.feed
  if (!feed?.stale) return ''
  const since = feed.last_success_at
    ? `since ${formatDateTime(feed.last_success_at)}`
    : 'since the backend started'
  return `Live price feed unavailable ${since}. Showing the last saved prices; Telegram updates are paused until it recovers.`
})

const feedAnnouncement = ref('')
let lastFeedState = null
watch(
  () => ({
    ready: Boolean(prices.value),
    live: feedLive.value,
    stale: Boolean(prices.value?.feed?.stale),
  }),
  (next) => {
    if (!next.ready) return
    const state = next.stale ? 'stale' : next.live ? 'live' : 'saved'
    if (lastFeedState === null) {
      lastFeedState = state
      return
    }
    if (state === lastFeedState) return
    lastFeedState = state
    feedAnnouncement.value = state === 'stale'
      ? 'Live price feed unavailable. Showing saved prices; Telegram updates are paused.'
      : state === 'live'
        ? 'Live price feed restored.'
        : 'Live price feed unavailable. Showing saved prices.'
  },
  { immediate: true },
)
const marketStatusText = computed(() => {
  if (!prices.value) return loading.value ? 'Checking market hours' : 'Market hours unavailable'
  return marketOpen.value ? 'MCX market open' : 'MCX market closed'
})
const providerName = computed(() => liveData.value?.XAU?.source || 'MCX futures')
const usdInr = computed(() => {
  // `liveData` is the metals map; the FX rate lives on the snapshot itself.
  const rate = Number(prices.value?.fx?.USD_INR)
  return Number.isFinite(rate) && rate > 0 ? rate.toFixed(4) : '-'
})
const telegramStatus = computed(() => {
  const status = logsData.value?.last_periodic_status
  if (status === 'failed') return 'Last attempt failed'
  if (status === 'pending' || status === 'sending') return 'Retrying delivery'
  if (logsData.value?.last_periodic_sent_at) return 'Delivered'
  return 'No update sent yet'
})
const nextSendText = computed(() => {
  if (prices.value?.feed?.stale) return 'Paused until the market feed returns'
  const value = logsData.value?.next_send_at
  const date = parseDate(value)
  if (!date) return 'Checking schedule'
  return date.getTime() <= Date.now() + 60000 ? 'Due now' : formatDateTime(value)
})

function changePercent(quote) {
  const open = Number(quote?.open)
  const close = Number(quote?.close)
  if (!Number.isFinite(open) || !Number.isFinite(close) || open <= 0) return null
  return ((close - open) / open) * 100
}

function changeClass(quote) {
  const change = changePercent(quote)
  if (change === null || change === 0) return 'change-neutral'
  return change > 0 ? 'change-up' : 'change-down'
}

function changeLabel(quote) {
  const change = changePercent(quote)
  if (change === null) return 'No earlier reading to compare'
  if (change === 0) return 'No change since the first reading today'
  return `${change > 0 ? '+' : ''}${change.toFixed(2)}% since the first reading today`
}

const deliveryAnnouncement = computed(() => {
  const statusMap = { failed: 'failed', sending: 'sending', pending: 'pending', sent: 'sent' }
  const status = logsData.value?.last_periodic_status
  if (!status) return ''
  const label = statusMap[status] || status
  const countMap = { pending: 'pending', sending: 'sending', failed: 'failed' }
  const pendingCount = (logsData.value?.logs || []).filter((log) => countMap[log.status]).length
  if (pendingCount) return `Delivery has ${pendingCount} ${pendingCount === 1 ? 'job' : 'jobs'} ${pendingCount === 1 ? 'pending' : 'pending'}`
  return `Delivery status: ${label}`
})

const dataAnnouncement = computed(() => {
  if (loading.value && !prices.value) return 'Loading chart data'
  if (error.value) return 'Data could not be loaded'
  if (chart.value?.labels?.length && logsData.value?.logs?.length) return 'Data loaded'
  return ''
})

const chartSummary = computed(() => {
  if (!chartRows.value.length) {
    return `No saved gold or silver observations are available for the selected ${chartRange.value} range.`
  }
  const first = chartRows.value[0]
  const latest = chartRows.value[chartRows.value.length - 1]
  return `${chartRange.value} history has ${chartRows.value.length} saved readings, from ${first.label} to ${latest.label}.`
})

function onRangeChange(range) {
  chartRange.value = range
  refreshChart(range)
}

</script>

<template>
  <div class="app">
    <a class="skip-link" href="#main">Skip to market prices</a>
    <HeaderBar :market-status="marketStatusText" />

    <main id="main" class="main dashboard-main" tabindex="-1" :aria-busy="!prices && loading ? 'true' : undefined">
      <section class="dashboard-intro">
        <div>
          <p class="dashboard-eyebrow">LIVE MCX PRICES</p>
          <h1>Gold and silver prices in India</h1>
          <p class="dashboard-lede">Front-month MCX futures in rupees, with COMEX spot and USD/INR for reference. All times are IST.</p>
        </div>
        <div class="feed-summary" :class="{ 'feed-summary-stale': !feedLive }">
          <span class="feed-light" aria-hidden="true"></span>
          <div class="feed-summary-copy">
            <strong>{{ feedStatus }}</strong>
            <span>Listens over WebSocket</span>
          </div>
          <div class="feed-summary-time">
            <span>Updated</span>
            <strong>{{ formatDateTime(prices?.captured_at) }}</strong>
          </div>
        </div>
      </section>

      <div v-if="error" class="dashboard-alert" role="alert">{{ error }}</div>
      <button type="button" class="retry-btn" @click="retryLoad()" :disabled="error === null">Retry load</button>
      <p class="sr-only" aria-live="polite" aria-atomic="true">{{ feedAnnouncement }}</p>
      <p class="sr-only" aria-live="polite" aria-atomic="true">{{ deliveryAnnouncement }}</p>
      <p class="sr-only" aria-live="polite" aria-atomic="true">{{ dataAnnouncement }}</p>
      <div v-if="feedAlert" class="dashboard-alert feed-alert" role="status">{{ feedAlert }}</div>
      <div v-if="!prices && loading" class="dashboard-empty" role="status">
        Connecting to the backend...
      </div>

      <section class="market-strip" aria-label="Market data status">
        <div class="strip-item">
          <span>Source</span>
          <strong class="provider-name">{{ providerName }}</strong>
        </div>
        <div class="strip-item">
          <span>USD / INR</span>
          <strong>{{ usdInr }}</strong>
        </div>
        <div class="strip-item">
          <span>Last saved reading</span>
          <strong>{{ latestSavedQuote?.label || 'No saved history yet' }}</strong>
        </div>
      </section>

      <section class="quote-grid" aria-label="Current MCX prices">
        <article class="quote-card gold-quote">
          <div class="quote-heading">
            <div>
              <span class="quote-symbol">MCX FRONT MONTH</span>
              <h2>Gold * Rs per 10 g</h2>
            </div>
            <span class="quote-state" :class="{ stale: !gold?.live }">
              {{ gold?.live ? 'Live' : 'Saved' }}
            </span>
          </div>
          <p class="quote-value">
            <span v-if="gold">{{ money(gold.close, 0) }}</span>
            <template v-else><span aria-hidden="true">-</span><span class="sr-only">Gold price unavailable</span></template>
          </p>
          <div class="quote-details">
            <span>{{ gold ? `${money(gold.inr_per_gram, 2)} / g` : 'Rs - / g' }}</span>
            <span>{{ gold?.usd_per_oz ? `COMEX $${Number(gold.usd_per_oz).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} / oz` : 'COMEX - / oz' }}</span>
          </div>
          <div class="quote-change" :class="changeClass(gold)">
            <span>Change today</span>
            <strong>{{ changeLabel(gold) }}</strong>
          </div>
        </article>

        <article class="quote-card silver-quote">
          <div class="quote-heading">
            <div>
              <span class="quote-symbol">MCX FRONT MONTH</span>
              <h2>Silver * Rs per 10 g</h2>
            </div>
            <span class="quote-state" :class="{ stale: !silver?.live }">
              {{ silver?.live ? 'Live' : 'Saved' }}
            </span>
          </div>
          <p class="quote-value">
            <span v-if="silver">{{ money(silver.close, 0) }}</span>
            <template v-else><span aria-hidden="true">-</span><span class="sr-only">Silver price unavailable</span></template>
          </p>
          <div class="quote-details">
            <span>{{ silver ? `${money(silver.inr_per_gram, 2)} / g` : 'Rs - / g' }}</span>
            <span>{{ silver?.usd_per_oz ? `COMEX $${Number(silver.usd_per_oz).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} / oz` : 'COMEX - / oz' }}</span>
          </div>
          <div class="quote-change" :class="changeClass(silver)">
            <span>Change today</span>
            <strong>{{ changeLabel(silver) }}</strong>
          </div>
        </article>
      </section>

      <section class="analysis-grid">
        <div class="analysis-main">
        <article class="panel chart-panel">
          <div class="panel-heading">
            <div>
              <p class="panel-eyebrow">PRICE HISTORY</p>
              <h2>Saved prices over time</h2>
              <p class="chart-caption">Each point is a saved reading - not a live quote.</p>
            </div>
            <div class="range-switch" role="group" aria-label="Chart range">
              <button type="button" :aria-pressed="chartRange === '1D'" aria-label="Last 1 day" title="Last 1 day" @click="onRangeChange('1D')">1D</button>
              <button type="button" :aria-pressed="chartRange === '7D'" aria-label="Last 7 days" title="Last 7 days" @click="onRangeChange('7D')">7D</button>
              <button type="button" :aria-pressed="chartRange === '30D'" aria-label="Last 30 days" title="Last 30 days" @click="onRangeChange('30D')">30D</button>
            </div>
          </div>

          <p class="sr-only" aria-live="polite">{{ chartSummary }}</p>
          <div
            class="chart-area"
            role="img"
            :aria-label="`Saved ${chartRange} history: gold futures in rupees per 10 grams, silver futures in rupees per gram`"
            :aria-describedby="chartRows.length ? undefined : 'history-empty'"
          >
            <PriceChart
              v-if="chart?.labels?.length"
              :labels="chart.labels"
              :gold-data="chart.gold"
              :silver-data="chart.silver"
              :live="chart.live"
            />
            <div v-else id="history-empty" class="history-empty">
              <strong>No saved readings in this range</strong>
              <span>Readings appear here once the backend records them.</span>
            </div>
          </div>

          <details v-if="chartRows.length" class="chart-data">
            <summary>View these readings as a table</summary>
            <span class="sr-only">Keyboard shortcut: <kbd>Tab</kbd> to move to the data table</span>
            <div class="chart-data-scroll" role="region" aria-label="Historical gold and silver prices" tabindex="0">
              <table>
                <caption class="sr-only">Saved gold and silver prices for the selected chart range</caption>
                <thead>
                  <tr>
                    <th scope="col">Date and time (IST)</th>
                    <th scope="col">Gold * Rs / 10 g</th>
                    <th scope="col">Silver * Rs / g</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in chartRows" :key="row.key">
                    <th scope="row">{{ row.label }}</th>
                    <td>{{ row.gold === null ? '-' : money(row.gold, 0) }}</td>
                    <td>{{ row.silver === null ? '-' : money(row.silver, 2) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </details>
        </article>

        <PurityTable :purity="purity?.purity || []" />
        <p class="pricing-note">
          MCX futures prices exclude GST, making charges and local premiums.
          Live prices stream over WebSocket; the chart draws the full history the
          backend stores, and Telegram posts once every 30 minutes when the feed is live.
        </p>
        </div>

        <aside class="delivery-column" aria-label="Telegram delivery status">
          <section class="delivery-summary">
            <div class="delivery-title">
              <div>
                <p class="panel-eyebrow">AUTOMATION</p>
                <h2>Telegram delivery</h2>
              </div>
              <span class="delivery-indicator" :class="logsData?.last_periodic_status || 'unknown'"></span>
            </div>
            <p class="delivery-state">{{ telegramStatus }}</p>
            <dl class="delivery-facts">
              <div>
                <dt>Last sent</dt>
                <dd>{{ formatDateTime(logsData?.last_periodic_sent_at) }}</dd>
              </div>
              <div>
                <dt>Next send</dt>
                <dd>{{ nextSendText }}</dd>
              </div>
              <div>
                <dt>Sends every</dt>
                <dd>{{ logsData?.interval_minutes || 30 }} minutes</dd>
              </div>
            </dl>
            <p class="delivery-note">Sends only when due. Missed intervals are not replayed.</p>
          </section>

          <NotificationLogs :logs="logsData?.logs || []" :source="logsData?.source" />
        </aside>
      </section>
    </main>
  </div>
</template>

<style scoped>
.retry-btn {
  align-self: flex-start;
  padding: 6px 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
  color: var(--ink-2);
  font-size: 12px;
  font-weight: 650;
}

.retry-btn:hover:not(:disabled) {
  border-color: var(--ink-2);
  color: var(--ink);
}

.retry-btn:disabled {
  opacity: .5;
  cursor: not-allowed;
}

.dashboard-main {
  max-width: 1440px;
  gap: 18px;
  padding: 30px 32px 48px;
}

.dashboard-intro {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
}

.dashboard-eyebrow,
.panel-eyebrow {
  margin: 0 0 7px;
  color: var(--gold);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .12em;
  text-transform: uppercase;
}

.dashboard-intro h1 {
  margin: 0;
  color: var(--ink);
  font-size: clamp(26px, 3vw, 36px);
  font-weight: 720;
  letter-spacing: -.04em;
  line-height: 1.1;
}

.dashboard-lede {
  margin: 8px 0 0;
  color: var(--mute);
  font-size: 13px;
}

.feed-summary {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 390px;
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--panel);
}

.feed-light,
.delivery-indicator {
  width: 9px;
  height: 9px;
  flex: none;
  border-radius: 50%;
  background: var(--up);
}

.feed-summary-stale .feed-light { background: var(--gold); }

.feed-summary-copy,
.feed-summary-time {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.feed-summary-copy { min-width: 160px; }
.feed-summary-copy strong,
.feed-summary-time strong { color: var(--ink); font-size: 12px; }
.feed-summary-copy span,
.feed-summary-time span {
  color: var(--mute);
  font-size: 11px;
}

.feed-summary-time {
  min-width: 142px;
  padding-left: 12px;
  border-left: 1px solid var(--line);
}

.dashboard-alert,
.dashboard-empty {
  padding: 11px 14px;
  border: 1px solid color-mix(in srgb, var(--gold) 32%, var(--line));
  border-radius: 9px;
  background: var(--gold-soft);
  color: var(--ink-2);
  font-size: 12px;
}

.dashboard-empty { border-color: var(--line); background: var(--panel); }

.market-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--panel);
}

.strip-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  padding: 12px 15px;
}

.strip-item + .strip-item { border-left: 1px solid var(--line); }
.strip-item span { color: var(--mute); font-size: 11px; }

.strip-item strong {
  color: var(--ink);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.provider-name { text-transform: uppercase; letter-spacing: .04em; }

.quote-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-auto-rows: 1fr;
  align-items: stretch;
  gap: 16px;
}

.quote-card {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 235px;
  padding: 20px 22px 15px;
  border: 1px solid var(--line);
  border-top: 3px solid var(--gold);
  border-radius: 11px;
  background: var(--panel);
}

.silver-quote { border-top-color: var(--silver); }
.quote-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; min-height: 42px; }
.quote-symbol { color: var(--mute); font-size: 11px; font-weight: 800; letter-spacing: .12em; }
.quote-heading h2 { margin: 5px 0 0; color: var(--ink-2); font-size: 13px; font-weight: 650; }
.quote-state { padding: 3px 8px; border-radius: 999px; background: var(--up-bg); color: var(--up); font-size: 11px; font-weight: 750; }
.quote-state.stale { background: var(--gold-soft); color: var(--gold); }

.quote-value {
  margin: 16px 0 10px;
  color: var(--ink);
  font-size: clamp(34px, 4vw, 46px);
  font-weight: 700;
  letter-spacing: -.045em;
  line-height: 1;
}

.quote-details { display: flex; flex-wrap: wrap; gap: 8px 18px; min-height: 18px; color: var(--ink-2); font-size: 12px; }
.quote-change { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-height: 44px; margin-top: auto; padding-top: 11px; border-top: 1px solid var(--line); font-size: 11px; }
.quote-change span { color: var(--mute); }
.quote-change strong { font-size: 11px; text-align: right; }
.change-up strong { color: var(--up); }
.change-down strong { color: var(--down); }
.change-neutral strong { color: var(--ink-2); }

.analysis-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.65fr) minmax(300px, .85fr);
  align-items: start;
  gap: 16px;
}

.analysis-main { display: grid; gap: 16px; min-width: 0; }

.chart-panel { min-width: 0; }
.panel-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 18px; padding: 17px 18px 13px; border-bottom: 1px solid var(--line); }
.panel-heading h2,
.delivery-title h2 { margin: 0; color: var(--ink); font-size: 17px; font-weight: 750; letter-spacing: -.02em; }
.panel-heading .panel-eyebrow,
.delivery-title .panel-eyebrow { margin-bottom: 4px; }
.panel-heading .chart-caption { max-width: 520px; margin-top: 5px; }

.range-switch { display: flex; flex: none; gap: 3px; padding: 3px; border: 1px solid var(--line); border-radius: 8px; background: var(--bg); }
.range-switch button { min-width: 40px; padding: 5px 8px; border: 0; border-radius: 5px; background: transparent; color: var(--mute); font-size: 11px; font-weight: 700; }
.range-switch button[aria-pressed="true"] { background: var(--panel); color: var(--ink); box-shadow: 0 1px 3px rgba(0, 0, 0, .1); }

.chart-area { min-height: 320px; padding: 7px 8px 0; }
.chart-area :deep(.chart-wrap) { height: 340px; }
.history-empty { min-height: 290px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; padding: 24px; color: var(--mute); text-align: center; }
.history-empty strong { color: var(--ink-2); font-size: 13px; }
.history-empty span { max-width: 380px; font-size: 12px; }

.chart-legends { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 4px 8px 0; color: var(--mute); font-size: 11px; }
.legend-row { display: inline-flex; align-items: center; gap: 6px; }
.legend-swatch { width: 13px; height: 3px; border-radius: 2px; }
.legend-dashed { border-top-style: dashed; }

.chart-data { margin: 0 17px 15px; color: var(--ink-2); font-size: 11px; }
.chart-data summary { padding: 8px 0; cursor: pointer; font-weight: 650; }
.chart-data .sr-only { padding: 6px 0; }
.chart-data-scroll { max-height: 280px; overflow: auto; }
.chart-data table { width: 100%; }

.delivery-column { display: grid; gap: 14px; min-width: 0; }
.delivery-summary { padding: 17px; border: 1px solid var(--line); border-radius: var(--radius); background: var(--panel); box-shadow: var(--shadow); }
.delivery-title { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.delivery-indicator.unknown { background: var(--mute); }
.delivery-indicator.pending,
.delivery-indicator.sending { background: var(--gold); }
.delivery-indicator.failed { background: var(--down); }
.delivery-state { margin: 14px 0 15px; color: var(--ink); font-size: 13px; font-weight: 700; }
.delivery-facts { margin: 0; }
.delivery-facts div { display: flex; flex-direction: column; gap: 3px; padding: 10px 0; border-top: 1px solid var(--line); }
.delivery-facts dt { color: var(--mute); font-size: 11px; }
.delivery-facts dd { margin: 0; color: var(--ink); font-size: 12px; font-weight: 650; }
.delivery-note { margin: 10px 0 0; color: var(--mute); font-size: 11px; line-height: 1.55; }
.delivery-column :deep(.panel) { min-width: 0; }

.pricing-note {
  max-width: 96ch;
  margin: 0;
  padding: 0 2px;
  color: var(--mute);
  font-size: 12px;
  line-height: 1.7;
}

@media (max-width: 1000px) {
  .dashboard-main { padding: 24px 20px 40px; }
  .analysis-grid { grid-template-columns: minmax(0, 1.25fr) minmax(270px, .85fr); }
  .feed-summary { min-width: 350px; }
}

@media (max-width: 760px) {
  .dashboard-main { gap: 14px; padding: 20px 14px 32px; }
  .dashboard-intro { align-items: stretch; flex-direction: column; gap: 14px; }
  .feed-summary { min-width: 0; }
  .market-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .strip-item:nth-child(3) {
    grid-column: 1 / -1;
    border-top: 1px solid var(--line);
    border-left: 0;
  }
  .quote-grid,
  .analysis-grid { grid-template-columns: minmax(0, 1fr); }
  .quote-card { padding: 17px; }
  .panel-heading { align-items: flex-start; flex-direction: column; }
}

@media (max-width: 460px) {
  .feed-summary { align-items: flex-start; flex-wrap: wrap; }
  .feed-summary-time { width: 100%; margin-left: 21px; padding: 8px 0 0; border-top: 1px solid var(--line); border-left: 0; }
  .strip-item { padding: 10px; }
  .strip-item strong { font-size: 11px; }
  .quote-value { font-size: 36px; }
}
</style>
