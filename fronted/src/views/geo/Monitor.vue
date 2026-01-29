<template>
  <div class="monitor-page" v-if="initialized">
    <!-- 1. 统计卡片 -->
    <div class="stats-grid">
      <div v-for="item in statConfigs" :key="item.label" :class="['stat-card', item.class]">
        <div class="stat-value">{{ item.value }}{{ item.unit }}</div>
        <div class="stat-label">{{ item.label }}</div>
      </div>
    </div>

    <el-row :gutter="20">
      <el-col :span="16">
        <!-- 检测操作 -->
        <div class="section">
          <div class="section-header">
            <h2 class="section-title">手动收录检测</h2>
            <el-button @click="refreshAllData" size="small" type="primary" plain>刷新数据</el-button>
          </div>
          <el-form :inline="true" :model="checkForm" class="check-form">
            <el-form-item label="项目">
              <el-select v-model="checkForm.projectId" placeholder="选择项目" style="width: 160px" @change="onProjectChange">
                <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="关键词">
              <el-select v-model="checkForm.keywordId" placeholder="选择关键词" style="width: 180px" :disabled="!checkForm.projectId">
                <el-option v-for="k in keywords" :key="k.id" :label="k.keyword || k.name" :value="k.id" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="checking" @click="runCheck">开始检测</el-button>
            </el-form-item>
          </el-form>
        </div>

        <!-- 趋势图表 -->
        <div class="section mt-20">
          <h2 class="section-title">收录命中率趋势</h2>
          <div ref="chartRef" style="width: 100%; height: 350px;"></div>
        </div>
      </el-col>

      <!-- 实时日志 -->
      <el-col :span="8">
        <div class="section log-section">
          <div class="section-header">
            <h2 class="section-title">流水线实时日志</h2>
            <el-tag :type="wsStatus === 'connected' ? 'success' : 'danger'" size="small">{{ wsStatus }}</el-tag>
          </div>
          <div class="log-console" ref="logRef">
            <div v-for="(log, index) in logs" :key="index" :class="['log-line', log.level]">
              <span class="log-time">{{ log.time }}</span>
              <span class="log-msg">{{ log.message }}</span>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import { geoKeywordApi, indexCheckApi, reportsApi } from '@/services/api'

// 状态声明
const initialized = ref(false)
const projects = ref<any[]>([])
const keywords = ref<any[]>([])
const logs = ref<any[]>([])
const wsStatus = ref('disconnected')
const stats = ref<any>({ total_keywords: 0, keyword_found: 0, company_found: 0, overall_hit_rate: 0 })
const checking = ref(false)
const logRef = ref<HTMLElement | null>(null)
const chartRef = ref<HTMLElement | null>(null)
let chartInstance: echarts.ECharts | null = null
let socket: WebSocket | null = null

const checkForm = ref({ projectId: null as any, keywordId: null as any, platforms: ['doubao'] })

// 统计配置
const statConfigs = computed(() => [
  { label: '监测关键词', value: stats.value.total_keywords || 0, unit: '', class: 'stat-blue' },
  { label: '关键词命中', value: stats.value.keyword_found || 0, unit: '', class: 'stat-green' },
  { label: '公司名命中', value: stats.value.company_found || 0, unit: '', class: 'stat-orange' },
  { label: '总体命中率', value: stats.value.overall_hit_rate || 0, unit: '%', class: 'stat-purple' }
])

// 1. 加载统计卡片
const loadStats = async () => {
  try {
    const res = await reportsApi.getOverview()
    stats.value = res.data || res || {}
  } catch (e) { console.error("加载卡片失败", e) }
}

// 2. 加载图表
const initChart = async () => {
  if (!chartRef.value) return
  if (chartInstance) chartInstance.dispose()
  chartInstance = echarts.init(chartRef.value)
  
  try {
    const res: any = await reportsApi.getTrends(30)
    const data = Array.isArray(res) ? res : (res?.data || [])
    
    chartInstance.setOption({
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'category', data: data.map((d: any) => d.date), axisLine: { lineStyle: { color: '#999' } } },
      yAxis: { type: 'value', splitLine: { lineStyle: { type: 'dashed' } } },
      series: [{ 
        name: '命中数', type: 'line', smooth: true, symbol: 'circle', symbolSize: 8,
        data: data.map((d: any) => d.keyword_found_count || 0),
        itemStyle: { color: '#67c23a' },
        areaStyle: { color: 'rgba(103, 194, 58, 0.1)' }
      }]
    })
  } catch (e) { console.error("图表渲染失败", e) }
}

// 3. 统一刷新方法
const refreshAllData = async () => {
  await loadStats()
  await initChart()
}

// 4. WebSocket (保持连接)
const initWebSocket = () => {
  socket = new WebSocket(`ws://127.0.0.1:8001/ws?client_id=mon_${Math.random().toString(36).slice(-5)}`)
  socket.onopen = () => { wsStatus.value = 'connected' }
  socket.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data && data.message) {
        logs.value.push({ time: data.time || '', level: data.level || 'INFO', message: data.message })
        if (logs.value.length > 50) logs.value.shift()
        nextTick(() => { if (logRef.value) logRef.value.scrollTop = logRef.value.scrollHeight })
      }
    } catch (e) {}
  }
  socket.onclose = () => { wsStatus.value = 'disconnected'; setTimeout(initWebSocket, 5000) }
}

const onProjectChange = async () => {
  keywords.value = []
  if (!checkForm.value.projectId) return
  try {
    const res: any = await geoKeywordApi.getProjectKeywords(checkForm.value.projectId)
    keywords.value = Array.isArray(res) ? res : (res?.data || [])
  } catch (e) { console.error(e) }
}

const runCheck = async () => {
  if (!checkForm.value.keywordId) return
  const project = projects.value.find(p => p.id === checkForm.value.projectId)
  checking.value = true
  try {
    const res = await indexCheckApi.check({
      keyword_id: checkForm.value.keywordId,
      company_name: project?.company_name || '',
      platforms: ['doubao']
    })
    if (res.success) {
      ElMessage.success('监测任务已提交，请等待日志更新')
      // 8秒后自动刷新数据
      setTimeout(refreshAllData, 8000)
    }
  } catch (e) { ElMessage.error('提交失败') }
  finally { checking.value = false }
}

onMounted(async () => {
  // 核心初始化顺序
  const pRes = await geoKeywordApi.getProjects()
  projects.value = Array.isArray(pRes) ? pRes : (pRes as any)?.data || []
  await loadStats()
  initialized.value = true // 显示页面
  nextTick(() => {
    initChart()
    initWebSocket()
  })
  window.addEventListener('resize', () => chartInstance?.resize())
})

onUnmounted(() => {
  if (socket) socket.close()
  if (chartInstance) chartInstance.dispose()
})
</script>

<style scoped>
.monitor-page { padding: 20px; background: #f5f7fa; min-height: 100vh; }
.stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-bottom: 20px; }
.stat-card { padding: 20px; border-radius: 12px; color: #fff; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
.stat-blue { background: linear-gradient(135deg, #409eff, #79bbff); }
.stat-green { background: linear-gradient(135deg, #67c23a, #95d475); }
.stat-orange { background: linear-gradient(135deg, #e6a23c, #eebe77); }
.stat-purple { background: linear-gradient(135deg, #909399, #b1b3b8); }
.stat-value { font-size: 28px; font-weight: bold; margin-bottom: 5px; }
.section { background: #fff; padding: 20px; border-radius: 8px; border: 1px solid #ebeef5; margin-bottom: 20px; }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }
.section-title { font-size: 16px; font-weight: bold; margin: 0; color: #303133; }
.log-console { height: 420px; background: #1a1a1a; color: #dcdfe6; padding: 10px; overflow-y: auto; font-family: 'Courier New', Courier, monospace; font-size: 12px; border-radius: 4px; }
.log-line { margin-bottom: 4px; border-bottom: 1px solid #2d2d2d; padding-bottom: 2px; }
.log-time { color: #888; margin-right: 8px; }
.log-line.SUCCESS { color: #67c23a; }
.log-line.ERROR { color: #f56c6c; }
</style>