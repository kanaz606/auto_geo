<template>
  <div class="data-report-page">
    <!-- 1. 顶部筛选区 -->
    <div class="filter-section card-box">
      <div class="filter-left">
        <el-select v-model="filters.project_id" placeholder="选择项目" clearable @change="loadData" class="project-select">
          <el-option
            v-for="item in projects"
            :key="item.id"
            :label="item.name"
            :value="item.id"
          />
        </el-select>
        <el-select v-model="filters.days" placeholder="时间范围" @change="loadData" class="time-select">
          <el-option label="近7天" :value="7" />
          <el-option label="近30天" :value="30" />
        </el-select>
      </div>
      <div class="filter-right">
        <el-radio-group v-model="filters.platform" @change="loadData" size="default">
          <el-radio-button label="">全平台</el-radio-button>
          <el-radio-button label="DeepSeek">DeepSeek</el-radio-button>
          <el-radio-button label="豆包">豆包</el-radio-button>
          <el-radio-button label="通义千问">通义千问</el-radio-button>
        </el-radio-group>
        <el-button @click="loadData" class="refresh-btn">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>
    </div>

    <!-- 2. 数据总览 -->
    <div class="summary-section card-box">
      <div class="section-header">
        <h3 class="section-title">数据总览</h3>
        <el-tooltip content="统计选定时间范围内的核心指标数据" placement="top">
          <el-icon class="info-icon"><InfoFilled /></el-icon>
        </el-tooltip>
      </div>
      <div class="stats-grid">
        <div class="stat-card blue">
          <div class="card-title">文章生成数</div>
          <div class="card-value">{{ stats.total_articles }}</div>
          <div class="card-footer">
            <span>普通: {{ stats.common_articles }}</span>
            <span>GEO: {{ stats.geo_articles }}</span>
          </div>
        </div>
        <div class="stat-card green">
          <div class="card-title">发布成功率</div>
          <div class="card-value">{{ stats.publish_success_rate }}%</div>
          <div class="card-footer">
            <span>成功: {{ stats.publish_success_count }}</span>
            <span>总数: {{ stats.publish_total_count }}</span>
          </div>
        </div>
        <div class="stat-card orange">
          <div class="card-title">关键词命中率</div>
          <div class="card-value">{{ stats.keyword_hit_rate }}%</div>
          <div class="card-footer">
            <span>命中: {{ stats.keyword_hit_count }}</span>
            <span>检测: {{ stats.keyword_check_count }}</span>
          </div>
        </div>
        <div class="stat-card grey">
          <div class="card-title">公司名命中率</div>
          <div class="card-value">{{ stats.company_hit_rate }}%</div>
          <div class="card-footer">
            <span>命中: {{ stats.company_hit_count }}</span>
            <span>检测: {{ stats.company_check_count }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 3. AI平台对比分析 -->
    <div class="chart-section card-box">
      <h3 class="section-title">AI平台对比分析</h3>
      <div ref="comparisonChartRef" class="comparison-chart"></div>
    </div>

    <!-- 4. 项目影响力排行榜 -->
    <div class="leaderboard-section card-box">
      <h3 class="section-title">项目影响力排行榜</h3>
      <el-table :data="projectLeaderboard" stripe style="width: 100%" class="dark-table">
        <el-table-column prop="rank" label="排名" width="80" align="center" />
        <el-table-column prop="project_name" label="品牌/项目" />
        <el-table-column prop="company_name" label="公司" />
        <el-table-column prop="content_volume" label="内容声量" align="center" />
        <el-table-column prop="ai_mention_rate" label="AI提及率" align="center">
          <template #default="{ row }">{{ row.ai_mention_rate }}%</template>
        </el-table-column>
        <el-table-column prop="brand_relevance" label="品牌关联度" align="center">
          <template #default="{ row }">{{ row.brand_relevance }}%</template>
        </el-table-column>
        <template #empty>
          <div class="empty-text">暂无数据</div>
        </template>
      </el-table>
    </div>

    <!-- 5. 高贡献内容分析 -->
    <div class="analysis-section card-box">
      <h3 class="section-title">高贡献内容分析 (AI引用源)</h3>
      <el-table :data="contentAnalysis" stripe style="width: 100%" class="dark-table">
        <el-table-column prop="rank" label="排名" width="80" align="center" />
        <el-table-column prop="title" label="文章标题" show-overflow-tooltip />
        <el-table-column prop="platform" label="发布平台" width="120" />
        <el-table-column prop="ai_contribution" label="AI引用贡献率" width="150" align="center">
          <template #default="{ row }">{{ row.ai_contribution }}%</template>
        </el-table-column>
        <el-table-column prop="publish_time" label="发布时间" width="180" align="center" />
        <template #empty>
          <div class="empty-text">暂无数据</div>
        </template>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { InfoFilled, Refresh } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { reportsApi, geoKeywordApi } from '@/services/api'

// 筛选状态
const filters = ref({
  project_id: null,
  days: 7,
  platform: ''
})

// 项目列表
const projects = ref<any[]>([])

// 统计数据
const stats = ref({
  total_articles: 0,
  common_articles: 0,
  geo_articles: 0,
  publish_success_rate: 0,
  publish_success_count: 0,
  publish_total_count: 0,
  keyword_hit_rate: 0,
  keyword_hit_count: 0,
  keyword_check_count: 0,
  company_hit_rate: 0,
  company_hit_count: 0,
  company_check_count: 0
})

// 排行榜数据
const projectLeaderboard = ref<any[]>([])
const contentAnalysis = ref<any[]>([])

// 图表 DOM
const comparisonChartRef = ref<HTMLElement | null>(null)
let comparisonChart: echarts.ECharts | null = null

// 加载数据
const loadData = async () => {
  try {
    // 加载卡片数据
    const statsRes = await reportsApi.getStats(filters.value)
    stats.value = statsRes

    // 加载对比分析图表
    const comparisonRes = await reportsApi.getPlatformComparison(filters.value)
    renderComparisonChart(comparisonRes)

    // 加载项目排行
    const leaderboardRes = await reportsApi.getProjectLeaderboard({ days: filters.value.days })
    projectLeaderboard.value = leaderboardRes

    // 加载内容分析
    const analysisRes = await reportsApi.getContentAnalysis(filters.value)
    contentAnalysis.value = analysisRes
  } catch (error) {
    console.error('加载报表数据失败:', error)
  }
}

// 渲染对比图表
const renderComparisonChart = (data: any[]) => {
  if (!comparisonChartRef.value) return
  
  if (!comparisonChart) {
    comparisonChart = echarts.init(comparisonChartRef.value)
  }

  const platforms = data.map(item => item.platform)
  const hitRates = data.map(item => item.hit_rate)

  const option = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' }
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: platforms,
      axisLabel: { color: '#888' },
      axisLine: { lineStyle: { color: '#333' } }
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#888', formatter: '{value}%' },
      splitLine: { lineStyle: { color: '#333' } }
    },
    series: [
      {
        name: '命中率',
        type: 'bar',
        data: hitRates,
        barWidth: '40%',
        itemStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: '#4a90e2' },
            { offset: 1, color: '#357abd' }
          ]),
          borderRadius: [4, 4, 0, 0]
        }
      }
    ]
  }

  comparisonChart.setOption(option)
}

onMounted(async () => {
  // 获取项目列表
  const projectsRes = await geoKeywordApi.getProjects()
  projects.value = projectsRes

  loadData()

  // 监听窗口调整
  window.addEventListener('resize', () => {
    comparisonChart?.resize()
  })
})
</script>

<style scoped lang="scss">
.data-report-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding-bottom: 40px;
}

.card-box {
  background: var(--bg-secondary);
  border-radius: 12px;
  padding: 24px;
  border: 1px solid var(--border);
}

.section-title {
  margin: 0 0 20px 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

/* 筛选区 */
.filter-section {
  display: flex;
  justify-content: space-between;
  align-items: center;

  .filter-left {
    display: flex;
    gap: 12px;
    
    .project-select { width: 200px; }
    .time-select { width: 120px; }
  }

  .filter-right {
    display: flex;
    align-items: center;
    gap: 16px;

    .refresh-btn {
      background: transparent;
      border-color: var(--border);
      color: var(--text-secondary);
      &:hover {
        color: var(--primary);
        border-color: var(--primary);
      }
    }
  }
}

/* 数据总览 */
.summary-section {
  .section-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 20px;
    .section-title { margin-bottom: 0; }
    .info-icon { color: var(--text-secondary); cursor: help; }
  }

  .stats-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 20px;
  }

  .stat-card {
    padding: 24px;
    border-radius: 12px;
    color: white;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    text-align: center;
    min-height: 160px;

    &.blue { background: linear-gradient(135deg, #4a90e2 0%, #357abd 100%); }
    &.green { background: linear-gradient(135deg, #4caf50 0%, #3d8b40 100%); }
    &.orange { background: linear-gradient(135deg, #ff9800 0%, #f57c00 100%); }
    &.grey { background: linear-gradient(135deg, #607d8b 0%, #455a64 100%); }

    .card-title { font-size: 14px; opacity: 0.9; margin-bottom: 12px; }
    .card-value { font-size: 36px; font-weight: 700; margin-bottom: 12px; }
    .card-footer {
      width: 100%;
      display: flex;
      justify-content: space-around;
      font-size: 12px;
      opacity: 0.8;
      border-top: 1px solid rgba(255,255,255,0.2);
      padding-top: 12px;
    }
  }
}

/* 图表区 */
.chart-section {
  .comparison-chart {
    height: 350px;
    width: 100%;
  }
}

/* 表格区 */
.dark-table {
  background: transparent !important;
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: var(--bg-tertiary);
  --el-table-row-hover-bg-color: var(--bg-tertiary);
  
  :deep(.el-table__header) th {
    background: #111 !important;
    color: #888;
    border-bottom: none;
  }

  :deep(.el-table__row) td {
    border-bottom: 1px solid #333;
    color: var(--text-primary);
  }
}

.empty-text {
  padding: 40px;
  color: var(--text-secondary);
  text-align: center;
}

:deep(.el-radio-button__inner) {
  background: transparent;
  border-color: var(--border);
  color: var(--text-secondary);
}

:deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background: #333;
  color: #fff;
  border-color: #333;
}
</style>
