<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useDashboard } from '../composables/useDashboard'

const props = defineProps({
  schedule: { type: Array, default: () => [] },
})

const dashboard = useDashboard()

const nextText = ref('Calculating…')

let timer = null

function computeNext() {
  const now = new Date()
  const tz = 'Asia/Kolkata'
  const nowStr = now.toLocaleString('en-US', { timeZone: tz })
  const nowHour = new Date(nowStr).getHours()
  const nowMin = new Date(nowStr).getMinutes()
  const nowDay = now.getDay() // 0=Sun..6=Sat
  const isWeekend = nowDay === 0 || nowDay === 6

  // Market hours: 9:00–23:55 IST, Mon–Fri
  const marketOpenTime = 9 * 60   // 9:00 in minutes
  const marketCloseTime = 23 * 60 + 55  // 23:55 in minutes
  const nowMins = nowHour * 60 + nowMin

  let nextEvent = null
  let nextDiff = Infinity

  for (const ev of props.schedule) {
    if (!ev.enabled) continue

    const [hh, mm] = ev.time.split(':').map(Number)
    const evMins = hh * 60 + mm
    const dayOffset = ev.days === 'Fri' ? 0 : 1  // Mon–Thu events

    // Check if today matches
    let candidateDay = nowDay
    let candidateDate = new Date(now)

    if (isWeekend) {
      // Skip to Monday
      const daysUntilMonday = 8 - nowDay  // 0=Sun -> 1, 6=Sat -> 2
      candidateDate.setDate(candidateDate.getDate() + daysUntilMonday)
      candidateDay = 1 // Monday
    } else if (ev.days === 'Mon–Fri' || ev.days === 'Mon–Thu') {
      // Today or next weekday
      if (nowDay <= 5 && evMins > nowMins) {
        // Today
      } else {
        // Tomorrow (or next weekday)
        candidateDate.setDate(candidateDate.getDate() + 1)
        candidateDay = candidateDate.getDay()
        if (candidateDay === 0 || candidateDay === 6) {
          candidateDate.setDate(candidateDate.getDate() + (candidateDay === 0 ? 1 : 2))
          candidateDay = candidateDate.getDay()
        }
      }
    } else if (ev.days === 'Fri') {
      // Next Friday
      let daysUntilFri = (5 - nowDay + 7) % 7
      if (daysUntilFri === 0 && evMins <= nowMins) daysUntilFri = 7
      candidateDate.setDate(candidateDate.getDate() + daysUntilFri)
      candidateDay = 5
    }

    if (!nextEvent || candidateDate.getTime() < nextDiff) {
      nextDiff = candidateDate.getTime()
      nextEvent = { ...ev, date: candidateDate }
    }
  }

  if (!nextEvent) {
    nextText.value = 'No upcoming events'
    return
  }

  const diff = nextEvent.date.getTime() - now.getTime()
  const absDiff = Math.abs(diff)
  const totalMins = Math.floor(absDiff / 60000)
  const days = Math.floor(totalMins / 1440)
  const hours = Math.floor((totalMins % 1440) / 60)
  const mins = totalMins % 60

  if (diff < 0) {
    nextText.value = `Market closed—next open in ${days}d ${hours}h ${mins}m`
  } else {
    nextText.value = `Next: ${nextEvent.name} in ${days}d ${hours}h ${mins}m`
  }
}

onMounted(() => {
  computeNext()
  timer = setInterval(computeNext, 10000)  // update every 10s
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <div class="panel">
    <div class="tabs">
      <h2 style="margin:0">Automatic schedule</h2>
      <span class="sub" id="nx">{{ nextText }}</span>
    </div>
    <div id="sched">
      <div
        v-for="event in schedule"
        :key="event.name"
        class="dest"
      >
        <div>
          {{ event.name }}
          <div class="sub" style="margin:0">
            {{ event.days }} · {{ event.time }} {{ event.zone }}
          </div>
        </div>
        <span class="pill" :class="event.enabled ? 'on' : 'off'">
          {{ event.enabled ? 'Enabled' : 'Off' }}
        </span>
      </div>
    </div>
    <p class="hint">
      Posts go out on their own. Weekend events are skipped, and Friday's close is sent as the weekly close.
    </p>
  </div>
</template>
