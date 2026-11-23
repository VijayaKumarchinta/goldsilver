<script setup>
import { ref, watch, nextTick } from 'vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  destinations: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue', 'save'])

const dialogRef = ref(null)
const localDests = ref([])

watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      localDests.value = props.destinations.map((d) => ({ ...d }))
      nextTick(() => dialogRef.value?.showModal())
    } else {
      dialogRef.value?.close()
    }
  },
)

function close() {
  emit('update:modelValue', false)
}

function save() {
  emit('save', {
    destinations: localDests.value,
  })
  emit('update:modelValue', false)
}
</script>

<template>
  <dialog
    ref="dialogRef"
    class="settings-dialog"
    aria-labelledby="settings-title"
    @close="close"
  >
    <form method="dialog">
      <h3 id="settings-title" style="margin-top:0">Settings</h3>

      <h3>Destinations</h3>
      <div id="ddest">
        <label
          v-for="(dest, i) in localDests"
          :key="dest.name"
          class="dest"
        >
          <span>
            {{ dest.name }}
            <span class="tg">{{ dest.platform }}</span>
          </span>
          <input
            class="sw d"
            type="checkbox"
            v-model="dest.enabled"
            :aria-label="'Enable ' + dest.name"
          />
        </label>
      </div>

      <p class="hint">Notifications use Indian Standard Time.</p>

      <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:14px">
        <button value="cancel" type="button" @click="close">Cancel</button>
        <button class="primary" type="button" value="save" @click="save">
          Save changes
        </button>
      </div>
    </form>
  </dialog>
</template>

<style scoped>
.settings-dialog {
  border: 1px solid var(--line);
  border-radius: 14px;
  background: var(--panel);
  color: var(--ink);
  padding: 20px;
  width: min(580px, 92vw);
}

.settings-dialog::backdrop {
  background: rgba(0, 0, 0, 0.45);
}

.settings-dialog h3 {
  font: 700 18px "Segoe UI", Arial, system-ui, sans-serif;
  margin: 14px 0 4px;
}

.settings-dialog input[type=time],
.settings-dialog select {
  font: inherit;
  background: var(--bg);
  color: var(--ink);
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 4px 8px;
}

.settings-dialog .hint {
  font-size: 12px;
  color: var(--mute);
  margin-top: 12px;
}

.settings-dialog .sw {
  appearance: none;
  width: 38px;
  height: 22px;
  border-radius: 12px;
  background: var(--line);
  position: relative;
  cursor: pointer;
  flex: none;
}

.settings-dialog .sw:checked {
  background: var(--up);
}

.settings-dialog .sw::after {
  content: '';
  position: absolute;
  top: 3px;
  left: 3px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #fff;
  transition: left 0.15s;
}

.settings-dialog .sw:checked::after {
  left: 19px;
}

.settings-dialog .sw:focus-visible {
  outline: 2px solid var(--gold);
  outline-offset: 2px;
}
</style>
