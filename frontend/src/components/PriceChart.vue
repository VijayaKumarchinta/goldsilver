<script setup>
import { computed, onMounted, onUnmounted, watch, ref } from 'vue'
const props = defineProps({
  labels: { type: Array, default: () => [] },
  goldData: { type: Array, default: () => [] },
  silverData: { type: Array, default: () => [] },
  live: { type: Boolean, default: false },
})

const chartContainer = ref(null)
let chartInstance = null
let echartsModule = null

const isDark = computed(() =>
  document.documentElement.getAttribute('data-theme') === 'dark'
)

function buildOption() {
  const dark = isDark.value
  const axisLine = dark ? '#252c37' : '#e5e7eb'
  const axisLabel = dark ? '#8a93a3' : '#6b7280'
  const goldLabel = dark ? '#e2bf79' : '#815515'
  const silverLabel = dark ? '#b5beca' : '#555f6e'

  const goldSeries = props.goldData.map((v, i) => [props.labels[i] || '', v])
  const silverSeries = props.silverData.map((v, i) => [props.labels[i] || '', v])

  if (!goldSeries.length) {
    return null
  }

  // Fit the axes to the data instead of anchoring at zero, otherwise a day of
  // small moves is drawn as one flat line against 0-1,26,000.
  const numeric = (series) => series.map((d) => d[1]).filter((v) => Number.isFinite(v) && v > 0)
  function rangeFor(values, fallback, step) {
    if (!values.length) return { min: fallback, max: fallback * 1.1 }
    const lo = Math.min(...values)
    const hi = Math.max(...values)
    const pad = Math.max((hi - lo) * 0.15, hi * 0.002)
    return {
      min: Math.max(0, Math.floor((lo - pad) / step) * step),
      max: Math.ceil((hi + pad) / step) * step,
    }
  }
  const goldRange = rangeFor(numeric(goldSeries), 10000, 100)
  const silverRange = rangeFor(numeric(silverSeries), 100, 0.5)

  function parseDate(value) {
    const date = new Date(String(value).replace(' ', 'T'))
    return Number.isNaN(date.getTime()) ? null : date
  }

  function formatTime(value) {
    const date = parseDate(value)
    if (!date) return value
    return date.toLocaleTimeString('en-IN', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
      timeZone: 'Asia/Kolkata',
    })
  }

  function formatDateTime(value) {
    const date = parseDate(value)
    if (!date) return value
    return date.toLocaleString('en-IN', {
      weekday: 'short',
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
      timeZone: 'Asia/Kolkata',
    })
  }

  function formatAxisLabel(value, seriesType) {
    const date = parseDate(value)
    if (!date) return value
    const hasAdjacent = (idx) => {
      const prev = props.labels[idx - 1]
      const next = props.labels[idx + 1]
      if (!prev || !next) return true
      const prevDate = parseDate(prev)
      const nextDate = parseDate(next)
      if (!prevDate || !nextDate) return true
      const diffMs = (nextDate - prevDate) / 2
      return diffMs > 3 * 3600 * 1000
    }
    const idx = props.labels.indexOf(value)
    if (idx === props.labels.length - 1) return formatTime(value)
    if (!hasAdjacent(idx)) return ''
    if (seriesType === 'date') {
      return date.toLocaleDateString('en-IN', {
        day: '2-digit',
        month: 'short',
        timeZone: 'Asia/Kolkata',
      })
    }
    return formatTime(value)
  }

  return {
    backgroundColor: 'transparent',
    animation: !window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    grid: { left: 62, right: 58, top: 42, bottom: 40 },
    // The two y-axis names already label the series; a legend would repeat them.
    legend: { show: false },
    tooltip: {
      trigger: 'axis',
      backgroundColor: dark ? '#1a212b' : '#ffffff',
      borderColor: dark ? '#252c37' : '#e5e7eb',
      textStyle: { color: dark ? '#e8eaee' : '#111827', fontSize: 12 },
      extraCssText: 'box-shadow: 0 4px 12px rgba(0,0,0,0.08); border-radius: 8px;',
      formatter: (params) => {
        if (!params || !params.length) return ''
        const goldParam = params.find((item) => item.seriesName === 'Gold futures (₹ / 10 g)')
        const silverParam = params.find((item) => item.seriesName === 'Silver futures (₹ / g)')
        const t = formatDateTime(params[0].axisValue || params[0].name || '')
        const goldVal = Array.isArray(goldParam?.value) ? goldParam.value[1] : (goldParam?.value ?? 0)
        const silverVal = Array.isArray(silverParam?.value) ? silverParam.value[1] : (silverParam?.value ?? 0)
        return `<div style="font-size:12px;padding:4px 2px">
          <div style="font-weight:700;margin-bottom:6px">${t} IST</div>
          <div style="color:${goldLabel}">Gold futures · ₹${goldVal.toLocaleString('en-IN')} / 10 g</div>
          <div style="color:${silverLabel}">Silver futures · ₹${silverVal.toLocaleString('en-IN')} / g</div>
        </div>`
      },
    },
    xAxis: {
      type: 'category',
      data: props.labels,
      axisLine: { lineStyle: { color: axisLine } },
      axisTick: { show: false },
      axisLabel: {
        color: axisLabel,
        fontSize: 11,
        fontFamily: 'Segoe UI, Arial, system-ui, sans-serif',
        interval: 'auto',
        formatter: (value) => formatAxisLabel(value, 'date'),
      },
      splitLine: { show: false },
    },
    yAxis: [
      {
        type: 'value',
        name: 'Gold (₹ / 10 g)',
        nameTextStyle: { color: goldLabel, fontSize: 11, fontWeight: 500, align: 'left' },
        position: 'left',
        min: goldRange.min,
        max: goldRange.max,
        splitNumber: 4,
        axisLine: { lineStyle: { color: axisLine } },
        axisTick: { show: false },
        axisLabel: {
          color: axisLabel,
          fontSize: 11,
          fontFamily: 'Segoe UI, Arial, system-ui, sans-serif',
          formatter: (v) => Number(v).toLocaleString('en-IN', { maximumFractionDigits: 0 }),
        },
        splitLine: {
          lineStyle: { color: dark ? '#252c37' : '#e5e7eb', type: 'dashed' },
        },
      },
      {
        type: 'value',
        name: 'Silver (₹ / g)',
        nameTextStyle: { color: silverLabel, fontSize: 11, fontWeight: 500, align: 'right' },
        position: 'right',
        min: silverRange.min,
        max: silverRange.max,
        splitNumber: 4,
        axisLine: { lineStyle: { color: axisLine } },
        axisTick: { show: false },
        axisLabel: {
          color: axisLabel,
          fontSize: 11,
          fontFamily: 'Segoe UI, Arial, system-ui, sans-serif',
          formatter: (v) => Number(v).toLocaleString('en-IN', { maximumFractionDigits: 2 }),
        },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: 'Gold futures (₹ / 10 g)',
        type: 'line',
        smooth: 0.35,
        symbol: 'circle',
        symbolSize: 5,
        // A single saved reading has no line segment; show the point instead.
        showSymbol: goldSeries.length <= 15,
        emphasis: { focus: 'series' },
        lineStyle: { color: '#a8741a', width: 2.5 },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: dark ? 'rgba(212,160,74,0.25)' : 'rgba(168,116,26,0.15)' },
              { offset: 1, color: 'transparent' },
            ],
          },
        },
        data: goldSeries,
        yAxisIndex: 0,
      },
      {
        name: 'Silver futures (₹ / g)',
        type: 'line',
        smooth: 0.35,
        symbol: 'circle',
        symbolSize: 4,
        showSymbol: silverSeries.length <= 15,
        emphasis: { focus: 'series' },
        lineStyle: { color: '#6b7280', width: 2, type: 'dashed' },
        data: silverSeries,
        yAxisIndex: 1,
      },
    ],
  }
}

async function initChart() {
  if (chartInstance) return
  if (!chartContainer.value) return
  const el = chartContainer.value
  if (el.clientWidth === 0 || el.clientHeight === 0) {
    setTimeout(initChart, 100)
    return
  }
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
  if (!echartsModule) {
    echartsModule = await import('echarts')
  }
  chartInstance = echartsModule.init(el)
  observeSize(el)
  const option = buildOption()
  if (option) {
    chartInstance.setOption(option, { notMerge: true })
  }
}

function updateChart() {
  if (!chartInstance) {
    initChart()
    return
  }
  const opt = buildOption()
  if (opt) {
    chartInstance.setOption(opt, { notMerge: true })
  }
}

let resizeTimer = null
let resizeObserver = null

function observeSize(el) {
  if (typeof ResizeObserver === 'undefined') return
  resizeObserver?.disconnect()
  resizeObserver = new ResizeObserver(() => chartInstance?.resize())
  resizeObserver.observe(el)
}

function handleResize() {
  if (resizeTimer) clearTimeout(resizeTimer)
  resizeTimer = setTimeout(() => {
    if (chartInstance && chartContainer.value) {
      chartInstance.resize()
    }
  }, 100)
}

onMounted(() => {
  initChart()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (resizeTimer) clearTimeout(resizeTimer)
  resizeObserver?.disconnect()
  resizeObserver = null
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
})

watch(
  () => [props.goldData, props.silverData, props.labels, isDark.value],
  () => updateChart(),
  { deep: true }
)
</script>

<template>
  <div>
    <div v-if="!labels.length" class="chart-placeholder">
      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M3 3v18h18"/>
        <path d="M7 14l4-4 4 2 5-6"/>
      </svg>
      <span>No historical data yet</span>
    </div>
    <div v-else ref="chartContainer" class="chart-wrap">
    </div>
  </div>
</template>
