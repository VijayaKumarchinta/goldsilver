import { ref, shallowRef } from 'vue'
import { io } from 'socket.io-client'

const apiBase = import.meta.env.VITE_API_BASE || '/api'
const socketOrigin = new URL(apiBase, window.location.origin).origin

// One shared connection for the whole app. The dashboard only listens to the
// server's broadcast; it never pushes prices back.
const socket = io(socketOrigin, {
  transports: ['websocket', 'polling'],
  autoConnect: true,
  reconnection: true,
  reconnectionAttempts: 10,
  reconnectionDelay: 1000,
  timeout: 20000,
})

const latest = shallowRef(null)
const connected = ref(socket.connected)
const error = ref(null)

// Listeners are registered once, when this module loads, so an event emitted
// before a component mounts is not missed.
socket.on('connect', () => {
  connected.value = true
  error.value = null
})

socket.on('disconnect', () => {
  connected.value = false
})

socket.on('price_update', (snapshot) => {
  if (!snapshot) return
  latest.value = snapshot
  error.value = null
})

socket.on('connect_error', (err) => {
  connected.value = false
  error.value = err?.message || 'Socket connection failed'
})

export function useSocket() {
  return { socket, latest, connected, error }
}
