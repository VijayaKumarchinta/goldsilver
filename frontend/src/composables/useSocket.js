import { ref, onMounted, onUnmounted, watch, shallowRef } from 'vue'
import { io } from 'socket.io-client'

// The dashboard subscribes to price events instead of polling REST. The
// backend emits every time the live TradingView quote is valid, so the
// chart, the quote cards and the feed status all update in real time.
const apiBase = import.meta.env.VITE_API_BASE || '/api'
const socketOrigin = new URL(apiBase, window.location.origin).origin

const socket = io(socketOrigin, {
  transports: ['websocket', 'polling'],
  autoConnect: true,
  reconnection: true,
  reconnectionAttempts: 10,
  reconnectionDelay: 1000,
  timeout: 20000,
})

export function useSocket() {
  const latest = shallowRef(null)
  const connected = ref(false)
  const error = ref(null)

  function handlePriceUpdate(snapshot) {
    latest.value = snapshot
    error.value = null
  }

  function handleConnect() {
    connected.value = true
    error.value = null
  }

  function handleDisconnect() {
    connected.value = false
  }

  function handleError(err) {
    error.value = err?.message || 'Socket error'
    connected.value = false
  }

  onMounted(() => {
    socket.on('connect', handleConnect)
    socket.on('disconnect', handleDisconnect)
    socket.on('price_update', handlePriceUpdate)
    socket.on('connect_error', handleError)
  })

  onUnmounted(() => {
    socket.off('connect', handleConnect)
    socket.off('disconnect', handleDisconnect)
    socket.off('price_update', handlePriceUpdate)
    socket.off('connect_error', handleError)
    try {
      socket.disconnect()
    } catch {
      // already closed
    }
  })

  return {
    socket,
    latest,
    connected,
    error,
  }
}
