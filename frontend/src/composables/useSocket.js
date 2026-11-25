import { ref, onMounted, onUnmounted, watch, shallowRef } from 'vue'
import { io } from 'socket.io-client'

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
  const acked = ref(false)
  const ackError = ref(null)

  // Server-side ack: the backend waits for the client to acknowledge
  // `price_update`, so the client knows the live quote was delivered
  // (no fire-and-forget).
  function handleAck(socketId, payload) {
    acked.value = true
    ackError.value = null
  }

  function handlePriceUpdate(snapshot) {
    latest.value = snapshot
    error.value = null

    // The dashboard is read-write. Once the live quote arrives, push a
    // delta back up to the server so the server marks it acked and can
    // credit/stale it on the delivery log. The server's ack callback
    // (useSocket.acked) confirms delivery to this client.
    sendPriceUpdate(socket.id)
      .catch(() => {
        // The push is best-effort. Reconnection/retry is owned by the
        // socket's auto-reconnect, so we do not block the live quote.
      })
  }

  function handleConnect() {
    connected.value = true
    acked.value = false
    ackError.value = null
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
    socket.on('ack', handleAck)
    socket.on('connect_error', handleError)
  })

  onUnmounted(() => {
    socket.off('connect', handleConnect)
    socket.off('disconnect', handleDisconnect)
    socket.off('price_update', handlePriceUpdate)
    socket.off('ack', handleAck)
    socket.off('connect_error', handleError)
    try {
      socket.disconnect()
    } catch {
    }
  })

  /**
   * Push a live price delta up to the server. The server waits for the
   * client's ack, then the dashboard credits the push and flags stale/injected
   * values.
   */
  async function sendPriceUpdate(delta) {
    if (!socket.connected) {
      error.value = 'Socket is not connected'
      return false
    }
    try {
      const response = await socket.emitWithAck('price_update', delta, { timeout: 15000 })
      acked.value = true
      ackError.value = null
      return response === true
    } catch (e) {
      acked.value = false
      ackError.value = e?.message || 'Price update timed out'
      error.value = ackError.value
      return false
    }
  }

  return {
    socket,
    latest,
    connected,
    error,
    acked,
    ackError,
    sendPriceUpdate,
  }
}
