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
      <h2 style="margin:0">Gold purity and silver rates</h2>
    </div>
    <div class="scroll" role="region" aria-label="Gold by purity and silver prices" tabindex="0">
      <table>
        <caption class="sr-only">Gold rates by purity and silver 999, per gram and per standard lot</caption>
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
    <p class="hint">22K and 18K rates are calculated from the 24K rate.</p>
  </div>
</template>
