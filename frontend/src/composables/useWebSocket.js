import { ref } from 'vue'

export function useWebSocket() {
  const messages = ref([])

  function onMessage(handler) {
    messages.value.push(handler)
  }

  function emit(data) {
    for (const handler of messages.value) {
      handler(data)
    }
  }

  return { messages, onMessage, emit }
}
