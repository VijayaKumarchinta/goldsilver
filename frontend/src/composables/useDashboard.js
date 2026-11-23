import { ref, computed, onMounted, onUnmounted } from 'vue'

const MCX_OPEN_HOUR = 9
const MCX_CLOSE_HOUR = 23
const MCX_CLOSE_MINUTE = 55

export function useDashboard() {
  const now = ref(new Date())
  let timer = null

  function tick() {
    now.value = new Date()
  }

  function startTimers() {
    tick()
    timer = setInterval(tick, 1000)
  }

  function stopTimers() {
    if (timer) clearInterval(timer)
  }

  onMounted(() => startTimers())
  onUnmounted(() => stopTimers())

  const marketStatus = computed(() => {
    const parts = new Intl.DateTimeFormat('en-IN', {
      timeZone: 'Asia/Kolkata',
      weekday: 'short',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).formatToParts(now.value)
    const part = (type) => parts.find((item) => item.type === type)?.value
    const weekday = part('weekday')
    const h = Number(part('hour')) % 24
    const m = Number(part('minute'))
    const day = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].indexOf(weekday)
    const isWeekend = day === 0 || day === 6

    if (isWeekend) return 'MCX closed for the weekend'
    const minutes = h * 60 + m
    if (minutes >= MCX_OPEN_HOUR * 60 && minutes <= MCX_CLOSE_HOUR * 60 + MCX_CLOSE_MINUTE) return 'MCX open'
    return 'MCX closed'
  })

  const marketOpen = computed(() => marketStatus.value === 'MCX open')

  const nextOpenText = computed(() => {
    const parts = new Intl.DateTimeFormat('en-IN', {
      timeZone: 'Asia/Kolkata',
      weekday: 'long',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).formatToParts(now.value)
    const weekday = parts.find((item) => item.type === 'weekday')?.value
    const h = Number(parts.find((item) => item.type === 'hour')?.value) % 24
    const m = Number(parts.find((item) => item.type === 'minute')?.value)
    const minutes = h * 60 + m

    if (marketOpen.value) return 'Closes 11:55 PM IST'
    if (minutes < MCX_OPEN_HOUR * 60 && !['Saturday', 'Sunday'].includes(weekday)) {
      return 'Next open today · 9:00 AM IST'
    }

    let nextDay = weekday === 'Friday' ? 'Monday' : weekday === 'Saturday' ? 'Monday' : weekday === 'Sunday' ? 'Monday' : 'tomorrow'
    if (weekday === 'Thursday') nextDay = 'Friday'
    else if (weekday === 'Monday' || weekday === 'Tuesday' || weekday === 'Wednesday') nextDay = 'tomorrow'
    return `Next open ${nextDay} · 9:00 AM IST`
  })

  const lastPriceTime = computed(() => {
    // filled in by parent from latest.captured_at
    return ''
  })

  function toggleTheme() {
    const html = document.documentElement
    const current = html.getAttribute('data-theme')
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    const next = (current === 'light' || (!current && !prefersDark)) ? 'dark' : 'light'
    html.setAttribute('data-theme', next)
    try { localStorage.setItem('theme', next) } catch(e) {}
  }

  function getTheme() {
    const html = document.documentElement
    return (
      html.getAttribute('data-theme') ||
      (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
    )
  }

  return {
    now,
    marketStatus,
    marketOpen,
    nextOpenText,
    lastPriceTime,
    toggleTheme,
    getTheme,
  }
}
