<script setup>
import { computed, onMounted, onUnmounted, watch, ref } from 'vue'
import { parseDateTime } from '../utils/format.js'
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
  const text = dark ? '#c5cbd3' : '#374151'
  const axisLine = dark ? '#252c37' : '#e5e7eb'
  const axisLabel = dark ? '#8a93a3' : '#6b7280'
  const goldLabel = dark ? '#e2bf79' : '#815515'
  const silverLabel = dark ? '#b5beca' : '#555f6e'

  const goldSeries = props.goldData.map((v, i) => [props.labels[i] || '', v])
  const silverSeries = props.silverData.map((v, i) => [props.labels[i] || '', v])
  const goldValues = goldSeries
    .map((point) => point[1])
    .filter((value) => value !== null && value !== undefined && Number.isFinite(Number(value)))
    .map(Number)
  const silverValues = silverSeries
    .map((point) => point[1])
    .filter((value) => value !== null && value !== undefined && Number.isFinite(Number(value)))
    .map(Number)

  if (!goldValues.length && !silverValues.length) {
    return null
  }

  function axisRange(values, step, minimumRange) {
    if (!values.length) return [0, step]
    const low = Math.min(...values)
    const high = Math.max(...values)
    const padding = Math.max(high - low, minimumRange) * 0.05
    const min = Math.floor((low - padding) / step) * step
    const max = Math.ceil((high + padding) / step) * step
    return [min, max > min ? max : min + step]
  }

  const [minGold, maxGold] = axisRange(goldValues, 500, 500)
  const [minSilver, maxSilver] = axisRange(silverValues, 1, 1)

  function formatTime(value) {
    const date = parseDateTime(value)
    if (!date) return value
    return date.toLocaleTimeString('en-IN', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
      timeZone: 'Asia/Kolkata',
    })
  }

  function formatDateTime(value) {
    const date = parseDateTime(value)
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

  return {
    backgroundColor: 'transparent',
    animation: !window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    grid: { left: 56, right: 56, top: 28, bottom: 40 },
    legend: {
      data: ['Gold 24K spot (₹ / 10 g)', 'Silver 999 spot (₹ / g)'],
      top: 6,
      right: 12,
      textStyle: {
        color: text,
        fontSize: 12,
        fontFamily: 'Segoe UI, Arial, system-ui, sans-serif',
        fontWeight: 500,
      },
      itemWidth: 16,
      itemHeight: 3,
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: dark ? '#1a212b' : '#ffffff',
      borderColor: dark ? '#252c37' : '#e5e7eb',
      textStyle: { color: dark ? '#e8eaee' : '#111827', fontSize: 12 },
      extraCssText: 'box-shadow: 0 4px 12px rgba(0,0,0,0.08); border-radius: 8px;',
      formatter: (params) => {
        if (!params || !params.length) return ''
        const goldParam = params.find((item) => item.seriesName === 'Gold 24K spot (₹ / 10 g)')
        const silverParam = params.find((item) => item.seriesName === 'Silver 999 spot (₹ / g)')
        const t = formatDateTime(params[0].axisValue || params[0].name || '')
        const formatValue = (param) => {
          const value = Array.isArray(param?.value) ? param.value[1] : param?.value
          return value === null || value === undefined || !Number.isFinite(Number(value))
            ? '—'
            : Number(value).toLocaleString('en-IN')
        }
        return `<div style="font-size:12px;padding:4px 2px">
          <div style="font-weight:700;margin-bottom:6px">${t} IST</div>
          <div style="color:${goldLabel}">Gold 24K spot · ₹${formatValue(goldParam)} / 10 g</div>
          <div style="color:${silverLabel}">Silver 999 spot · ₹${formatValue(silverParam)} / g</div>
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
        formatter: formatTime,
      },
      splitLine: { show: false },
    },
    yAxis: [
      {
        type: 'value',
        name: 'Gold 24K spot (₹ / 10 g)',
        nameTextStyle: { color: goldLabel, fontSize: 11, fontWeight: 500 },
        position: 'left',
        min: minGold,
        max: maxGold,
        axisLine: { lineStyle: { color: axisLine } },
        axisTick: { show: false },
        axisLabel: {
          color: axisLabel,
          fontSize: 11,
          fontFamily: 'Segoe UI, Arial, system-ui, sans-serif',
          formatter: '{value}',
        },
        splitLine: {
          lineStyle: { color: dark ? '#252c37' : '#e5e7eb', type: 'dashed' },
        },
      },
      {
        type: 'value',
        name: '',
        position: 'right',
        min: minSilver,
        max: maxSilver,
        axisLine: { lineStyle: { color: axisLine } },
        axisTick: { show: false },
        axisLabel: {
          color: axisLabel,
          fontSize: 11,
          fontFamily: 'Segoe UI, Arial, system-ui, sans-serif',
        },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: 'Gold 24K spot (₹ / 10 g)',
        type: 'line',
        smooth: 0.35,
        symbol: 'circle',
        symbolSize: 5,
        showSymbol: false,
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
        connectNulls: false,
      },
      {
        name: 'Silver 999 spot (₹ / g)',
        type: 'line',
        smooth: 0.35,
        symbol: 'circle',
        symbolSize: 4,
        showSymbol: false,
        emphasis: { focus: 'series' },
        lineStyle: { color: '#6b7280', width: 2, type: 'dashed' },
        data: silverSeries,
        yAxisIndex: 1,
        connectNulls: false,
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
