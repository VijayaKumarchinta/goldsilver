<script setup>
import { computed } from 'vue'

const props = defineProps({
  logs: { type: Array, default: () => [] },
  source: { type: String, default: 'db' },
})

// When every entry went to the same chat, name it once in the header instead of
// repeating it on every row.
const sharedDestination = computed(() => {
  const names = new Set(props.logs.map((log) => log.destination).filter(Boolean))
  return names.size === 1 ? [...names][0] : null
})

function pillClass(status) {
  if (status === 'sent') return 'pill sent'
  if (status === 'failed') return 'pill failed'
  if (status === 'sending') return 'pill sending'
  if (status === 'delivered') return 'pill sent'
  return 'pill'
}

function statusLabel(status) {
  if (!status) return '—'
  return status.charAt(0).toUpperCase() + status.slice(1)
}

function eventLabel(eventType) {
  const labels = {
    periodic_update: '30-minute price update',
    hourly_update: 'Hourly market update',
    hourly: 'Hourly market update',
    market_open: 'Market open',
    market_close: 'Market close',
    weekly_close: 'Weekly close',
  }
  return labels[eventType] || eventType || 'Notification'
}

function formatTime(iso) {
  if (!iso) return ''
  if (!iso.includes('T') && !iso.includes('-')) return iso
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return iso
    return d.toLocaleString('en-IN', {
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
      timeZone: 'Asia/Kolkata',
      hour12: false,
    })
  } catch {
    return iso
  }
}
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <h2 id="notification-log-heading">Telegram Notifications</h2>
      <span class="panel-sub">
        {{ logs.length }} notification{{ logs.length !== 1 ? 's' : '' }}
        <template v-if="sharedDestination"> · {{ sharedDestination }}</template>
        <template v-else-if="source"> · {{ source }}</template>
      </span>
    </div>
    <div class="panel-body">
      <div v-if="!logs.length" class="empty">No notifications sent yet.</div>
      <section
        v-else
        class="log-region"
        aria-labelledby="notification-log-heading"
        tabindex="0"
      >
        <ul class="log-list" :class="{ 'single-destination': sharedDestination }">
          <li v-for="log in logs" :key="log.id || log.time" class="log-row">
            <div class="log-event">
              <div class="log-event-name">{{ eventLabel(log.event_type || log.event) }}</div>
              <div class="log-meta">
                {{ formatTime(log.sent_at || log.updated_at || log.created_at || log.time) }}
              </div>
              <div v-if="log.note" class="log-meta">{{ log.note }}</div>
              <div v-if="log.last_error" class="log-meta">{{ log.last_error }}</div>
            </div>
            <div v-if="!sharedDestination" class="log-dest">
              <div class="dest-name">{{ log.destination }}</div>
            </div>
            <span :class="pillClass(log.status)" class="status-pill">{{ statusLabel(log.status) }}</span>
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>
