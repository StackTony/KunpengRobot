<script setup lang="ts">
/* ECharts 通用封装：传 option 自动渲染 + 自适应尺寸 + 点击事件转发 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps<{ option: echarts.EChartsOption; height?: string }>()
const emit = defineEmits(['chartClick'])

const el = ref<HTMLDivElement>()
let chart: echarts.ECharts | null = null
let ro: ResizeObserver | null = null

function render() {
  if (!el.value) return
  if (!chart) {
    chart = echarts.init(el.value)
    ro = new ResizeObserver(() => chart?.resize())
    ro.observe(el.value)
    chart.on('click', (params: any) => emit('chartClick', params))
  }
  chart.setOption(props.option, true)
}

onMounted(render)
watch(() => props.option, render, { deep: true })
onBeforeUnmount(() => {
  ro?.disconnect()
  chart?.dispose()
})
</script>

<template>
  <div ref="el" class="chart-box" :style="{ height: height ?? '300px' }" />
</template>

<style scoped>
.chart-box {
  width: 100%;
}
</style>
