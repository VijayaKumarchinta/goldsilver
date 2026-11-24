<script setup>
import { computed } from 'vue'
import { money } from '../utils/format.js'

const props = defineProps({
  purity: { type: Array, default: () => [] },
})

const rows = computed(() => props.purity)
</script>

<template>
  <div class="panel">
    <div class="tabs">
      <h2 style="margin:0">Gold by purity and silver</h2>
    </div>
    <div class="scroll">
      <table>
        <thead>
          <tr>
            <th scope="col">Item</th>
            <th scope="col">Per gram</th>
            <th scope="col">Standard lot</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.label">
            <th scope="row">{{ row.label }}</th>
            <td>{{ money(parseFloat(row.per_gram), 2) }}</td>
            <td>{{ money(parseFloat(row.per_lot), 0) }} {{ row.unit }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="hint">Lower purities are estimates derived from the MCX gold price. GST, making charges and local premiums are not included.</p>
  </div>
</template>
