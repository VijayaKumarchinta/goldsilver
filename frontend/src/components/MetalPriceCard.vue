<script setup>
import { computed } from 'vue'
import { money } from '../utils/format.js'

const props = defineProps({
  metal: { type: String, required: true },
  name: { type: String, required: true },
  perGram: { type: String, required: true },
  usdPerOz: { type: String, required: true },
  providerUpdatedAt: { type: String, required: true },
  unit: { type: String, default: 'g' },
  accent: { type: Boolean, default: false },
})

const metalClass = computed(() => props.metal === 'XAU' ? 'gold' : 'silver')
const isUsd = computed(() => props.metal === 'USD')

const per10gNum = computed(() => {
  const v = parseFloat(props.perGram)
  return isNaN(v) ? 0 : v * 10
})

const perGramNum = computed(() => {
  const v = parseFloat(props.perGram)
  return isNaN(v) ? 0 : v
})

const usdNum = computed(() => {
  const v = parseFloat(props.usdPerOz)
  return isNaN(v) ? 0 : v
})

const bigPrice = computed(() => {
  if (isUsd.value) return '$' + usdNum.value.toFixed(2)
  return money(per10gNum.value, 0)
})

const unitLabel = computed(() => {
  if (isUsd.value) return '/ oz'
  return `/ 10 g`
})

const subValue = computed(() => {
  if (isUsd.value) return '$' + perGramNum.value.toFixed(2) + ' / g'
  return '₹' + perGramNum.value.toFixed(2) + ' / g'
})

const updatedAtDisplay = computed(() => {
  try {
    return new Date(props.providerUpdatedAt).toLocaleTimeString('en-IN', {
      timeZone: 'Asia/Kolkata',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    })
  } catch {
    return props.providerUpdatedAt
  }
})

const metricIcon = computed(() => {
  if (isUsd.value) return 'usd'
  return metalClass.value
})
</script>

<template>
  <div class="metric-card" :class="{ accent }">
    <div class="metric-head">
      <span class="metric-label">{{ name }}</span>
      <span class="metric-icon" :class="metricIcon">
        <svg v-if="isUsd" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="9"/>
          <path d="M12 7v5l3 1.5"/>
        </svg>
        <svg v-else-if="metalClass === 'gold'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="7" width="18" height="10" rx="2"/>
          <path d="M3 11h18M8 7v10"/>
        </svg>
        <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="9"/>
          <path d="M12 8v8M8 12h8"/>
        </svg>
      </span>
    </div>

    <p class="metric-value">{{ bigPrice }}<span style="font-size:16px;font-weight:600;color:var(--mute)">{{ unitLabel }}</span></p>

    <p class="metric-sub">{{ subValue }}</p>

    <div style="margin-top:8px;display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap">
      <span class="metric-badge neutral">Live</span>
      <span style="font-size:11px;color:var(--mute)">Updated {{ updatedAtDisplay }} IST</span>
    </div>
  </div>
</template>
