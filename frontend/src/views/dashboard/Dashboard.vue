<template>
  <div class="dashboard-container">
    <h2 class="page-title">仪表盘</h2>

    <!-- 概览卡片 -->
    <el-row :gutter="20" class="stat-cards">
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover" class="stat-card stat-card--primary">
          <div class="stat-card__body">
            <div class="stat-card__icon">
              <el-icon :size="28"><User /></el-icon>
            </div>
            <div class="stat-card__info">
              <div class="stat-card__label">今日新线索</div>
              <div class="stat-card__value">{{ overview.today_leads }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover" class="stat-card stat-card--warning">
          <div class="stat-card__body">
            <div class="stat-card__icon">
              <el-icon :size="28"><Star /></el-icon>
            </div>
            <div class="stat-card__info">
              <div class="stat-card__label">高意向线索</div>
              <div class="stat-card__value">{{ overview.today_high_intent }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover" class="stat-card stat-card--success">
          <div class="stat-card__body">
            <div class="stat-card__icon">
              <el-icon :size="28"><CircleCheck /></el-icon>
            </div>
            <div class="stat-card__info">
              <div class="stat-card__label">今日转化</div>
              <div class="stat-card__value">{{ overview.today_converted }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover" class="stat-card stat-card--danger">
          <div class="stat-card__body">
            <div class="stat-card__icon">
              <el-icon :size="28"><Bell /></el-icon>
            </div>
            <div class="stat-card__info">
              <div class="stat-card__label">待跟进</div>
              <div class="stat-card__value">{{ overview.pending_followup }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 今日API用量 -->
    <el-card class="section-card">
      <template #header>
        <div class="card-header">
          <span>今日API用量</span>
        </div>
      </template>
      <el-row :gutter="20">
        <el-col :xs="24" :sm="12" v-for="(quota, key) in quotaData" :key="key">
          <div class="quota-item">
            <div class="quota-item__header">
              <span class="quota-item__label">{{ apiTypeLabel(key) }}</span>
              <span class="quota-item__count">{{ quota.usage }} / {{ quota.limit }}</span>
            </div>
            <el-progress
              :percentage="quota.usage_rate"
              :color="getQuotaColor(quota.usage_rate)"
              :stroke-width="18"
              :text-inside="true"
            />
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- 私信队列统计卡片 -->
    <el-row :gutter="20" class="stat-cards">
      <el-col :xs="12" :sm="8">
        <el-card shadow="hover" class="stat-card stat-card--primary">
          <div class="stat-card__body">
            <div class="stat-card__icon">
              <el-icon :size="28"><Promotion /></el-icon>
            </div>
            <div class="stat-card__info">
              <div class="stat-card__label">今日私信已发</div>
              <div class="stat-card__value">
                {{ dmStats.daily_sent }}
                <span class="stat-card__limit">/ {{ dmStats.daily_limit }}</span>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8">
        <el-card shadow="hover" class="stat-card stat-card--warning">
          <div class="stat-card__body">
            <div class="stat-card__icon">
              <el-icon :size="28"><Clock /></el-icon>
            </div>
            <div class="stat-card__info">
              <div class="stat-card__label">队列等待中</div>
              <div class="stat-card__value">{{ dmStats.pending }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8">
        <el-card shadow="hover" class="stat-card stat-card--info">
          <div class="stat-card__body">
            <div class="stat-card__icon">
              <el-icon :size="28"><Calendar /></el-icon>
            </div>
            <div class="stat-card__info">
              <div class="stat-card__label">明日溢出待发</div>
              <div class="stat-card__value">{{ dmStats.overflow_tomorrow }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 风控状态卡片 -->
    <el-card class="section-card risk-card" :class="`risk-card--${riskStatus.level}`">
      <template #header>
        <div class="card-header">
          <span>私信风控状态</span>
          <el-tag :type="riskTagType(riskStatus.level)" size="small">
            {{ riskLevelLabel(riskStatus.level) }}
          </el-tag>
        </div>
      </template>
      <el-row :gutter="20">
        <el-col :xs="12" :sm="6">
          <div class="risk-stat">
            <div class="risk-stat__label">今日发送</div>
            <div class="risk-stat__value">{{ riskStatus.sent_count }}</div>
          </div>
        </el-col>
        <el-col :xs="12" :sm="6">
          <div class="risk-stat">
            <div class="risk-stat__label">举报数</div>
            <div class="risk-stat__value risk-stat__value--danger">{{ riskStatus.report_count }}</div>
          </div>
        </el-col>
        <el-col :xs="12" :sm="6">
          <div class="risk-stat">
            <div class="risk-stat__label">拉黑数</div>
            <div class="risk-stat__value risk-stat__value--danger">{{ riskStatus.block_count }}</div>
          </div>
        </el-col>
        <el-col :xs="12" :sm="6">
          <div class="risk-stat">
            <div class="risk-stat__label">举报拉黑率</div>
            <div
              class="risk-stat__value"
              :class="{ 'risk-stat__value--danger': riskStatus.report_rate > 0.007 }"
            >
              {{ riskStatus.report_rate_pct }}
            </div>
          </div>
        </el-col>
      </el-row>
      <div v-if="riskStatus.is_paused" class="risk-alert">
        <el-alert title="发送已熔断暂停" type="error" :closable="false" show-icon>
          举报拉黑率超过临界阈值，私信发送已自动暂停。需管理员确认后手动恢复。
        </el-alert>
        <el-button
          v-if="isAdmin"
          type="danger"
          style="margin-top: 12px"
          :loading="resuming"
          @click="handleResumeSending"
        >
          恢复发送
        </el-button>
      </div>
      <div v-else-if="riskStatus.is_throttled" class="risk-alert">
        <el-alert title="发送已降量" type="warning" :closable="false" show-icon>
          举报拉黑率超过预警阈值，已自动降量至50%。
        </el-alert>
      </div>
    </el-card>

    <!-- 趋势图 -->
    <el-card class="section-card">
      <template #header>
        <div class="card-header">
          <span>数据趋势</span>
          <el-radio-group v-model="trendDays" size="small" @change="fetchTrend">
            <el-radio-button :value="7">7天</el-radio-button>
            <el-radio-button :value="14">14天</el-radio-button>
            <el-radio-button :value="30">30天</el-radio-button>
          </el-radio-group>
        </div>
      </template>
      <div class="chart-wrapper">
        <v-chart :option="chartOption" autoresize style="height: 360px" />
      </div>
    </el-card>

    <!-- 销售业绩表格 (admin only) -->
    <el-card v-if="isAdmin" class="section-card">
      <template #header>
        <div class="card-header">
          <span>销售业绩</span>
          <div class="date-filter">
            <el-date-picker
              v-model="salesDateRange"
              type="daterange"
              range-separator="至"
              start-placeholder="开始日期"
              end-placeholder="结束日期"
              value-format="YYYY-MM-DD"
              size="small"
              @change="fetchSalesPerformance"
            />
          </div>
        </div>
      </template>
      <el-table :data="salesData" stripe style="width: 100%">
        <el-table-column prop="username" label="销售姓名" min-width="120" />
        <el-table-column prop="total_leads" label="总线索" min-width="100" />
        <el-table-column prop="high_intent" label="高意向" min-width="100" />
        <el-table-column prop="converted" label="已转化" min-width="100" />
        <el-table-column label="转化率" min-width="160">
          <template #default="{ row }">
            <el-progress :percentage="row.conversion_rate" :stroke-width="16" :text-inside="true" />
          </template>
        </el-table-column>
        <el-table-column label="平均响应时长" min-width="130">
          <template #default="{ row }">
            {{ row.avg_response_hours > 0 ? row.avg_response_hours + 'h' : '-' }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 监控效果表格 -->
    <el-card class="section-card">
      <template #header>
        <div class="card-header">
          <span>监控效果</span>
        </div>
      </template>
      <el-table :data="monitorData" stripe style="width: 100%">
        <el-table-column prop="nickname" label="监控账号" min-width="140" />
        <el-table-column prop="total_comments" label="评论总量" min-width="110" sortable />
        <el-table-column prop="total_leads" label="产出线索" min-width="110" sortable />
        <el-table-column label="线索率" min-width="110" sortable sort-by="lead_rate">
          <template #default="{ row }">
            <el-tag :type="row.lead_rate > 10 ? 'success' : row.lead_rate > 5 ? 'warning' : 'info'" size="small">
              {{ row.lead_rate }}%
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 导出按钮 (admin) -->
    <div v-if="isAdmin" class="export-section">
      <el-button type="primary" :icon="Download" :loading="exporting" @click="handleExport">
        导出线索数据 Excel
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
} from 'echarts/components'
import VChart from 'vue-echarts'
import { User, Star, CircleCheck, Bell, Download, Promotion, Clock, Calendar } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import {
  getDashboard,
  getSalesPerformance,
  getMonitorStats,
  getTrend,
  exportLeads,
} from '@/api/stats'
import { getDmQueueStats } from '@/api/dmQueue'
import { getQuotas } from '@/api/system'
import { getRiskStatus, resumeSending } from '@/api/risk'

use([CanvasRenderer, LineChart, TitleComponent, TooltipComponent, LegendComponent, GridComponent])

const userStore = useUserStore()
const isAdmin = computed(() => userStore.role === 'admin')

// 概览数据
const overview = ref({
  today_leads: 0,
  today_high_intent: 0,
  today_converted: 0,
  pending_followup: 0,
  today_comments: 0,
})

// 私信队列统计
const dmStats = ref({
  daily_sent: 0,
  daily_limit: 4000,
  global_limit: 5000,
  pending: 0,
  overflow_tomorrow: 0,
  total_sent: 0,
  total_failed: 0,
  is_paused: false,
})

// API配额数据
const quotaData = ref<Record<string, any>>({})

// 风控状态
const riskStatus = ref({
  level: 'normal',
  is_paused: false,
  is_throttled: false,
  report_rate: 0,
  report_rate_pct: '0.00%',
  sent_count: 0,
  read_count: 0,
  reply_count: 0,
  report_count: 0,
  block_count: 0,
  wechat_added_count: 0,
  effective_daily_limit: 4000,
  daily_limit: 4000,
})
const resuming = ref(false)

// 趋势数据
const trendDays = ref(7)
const trendData = ref<any[]>([])

// 销售业绩
const salesDateRange = ref<string[]>([])
const salesData = ref<any[]>([])

// 监控效果
const monitorData = ref<any[]>([])

// 导出状态
const exporting = ref(false)

// ECharts option
const chartOption = computed(() => ({
  tooltip: {
    trigger: 'axis',
  },
  legend: {
    data: ['新评论', '新线索', '高意向', '转化'],
    bottom: 0,
  },
  grid: {
    left: '3%',
    right: '4%',
    bottom: '12%',
    top: '5%',
    containLabel: true,
  },
  xAxis: {
    type: 'category',
    boundaryGap: false,
    data: trendData.value.map((d: any) => d.date.slice(5)),
  },
  yAxis: {
    type: 'value',
    minInterval: 1,
  },
  series: [
    {
      name: '新评论',
      type: 'line',
      smooth: true,
      data: trendData.value.map((d: any) => d.comments),
      itemStyle: { color: '#409eff' },
    },
    {
      name: '新线索',
      type: 'line',
      smooth: true,
      data: trendData.value.map((d: any) => d.leads),
      itemStyle: { color: '#67c23a' },
    },
    {
      name: '高意向',
      type: 'line',
      smooth: true,
      data: trendData.value.map((d: any) => d.high_intent),
      itemStyle: { color: '#e6a23c' },
    },
    {
      name: '转化',
      type: 'line',
      smooth: true,
      data: trendData.value.map((d: any) => d.converted),
      itemStyle: { color: '#f56c6c' },
    },
  ],
}))

async function fetchDashboard() {
  try {
    const res = await getDashboard()
    if (res.code === 200) {
      overview.value = res.data
    }
  } catch (e) {
    console.error('Failed to fetch dashboard', e)
  }
}

async function fetchTrend() {
  try {
    const res = await getTrend(trendDays.value)
    if (res.code === 200 && res.data?.data) {
      trendData.value = res.data.data
    }
  } catch (e) {
    console.error('Failed to fetch trend', e)
  }
}

async function fetchSalesPerformance() {
  if (!isAdmin.value) return
  try {
    const params: any = {}
    if (salesDateRange.value && salesDateRange.value.length === 2) {
      params.start_date = salesDateRange.value[0]
      params.end_date = salesDateRange.value[1]
    }
    const res = await getSalesPerformance(params)
    if (res.code === 200) {
      salesData.value = res.data
    }
  } catch (e) {
    console.error('Failed to fetch sales performance', e)
  }
}

async function fetchMonitorStats() {
  try {
    const res = await getMonitorStats()
    if (res.code === 200) {
      monitorData.value = res.data
    }
  } catch (e) {
    console.error('Failed to fetch monitor stats', e)
  }
}

async function fetchDmStats() {
  try {
    const res = await getDmQueueStats()
    if (res.code === 200) {
      dmStats.value = res.data
    }
  } catch (e) {
    console.error('Failed to fetch DM queue stats', e)
  }
}

async function fetchQuotas() {
  try {
    const res = await getQuotas()
    if (res.code === 200) {
      quotaData.value = res.data
    }
  } catch (e) {
    console.error('Failed to fetch quotas', e)
  }
}

async function fetchRiskStatus() {
  try {
    const res = await getRiskStatus()
    if (res.code === 200) {
      riskStatus.value = { ...riskStatus.value, ...res.data }
    }
  } catch (e) {
    console.error('Failed to fetch risk status', e)
  }
}

function riskTagType(level: string): 'success' | 'warning' | 'danger' | 'info' {
  switch (level) {
    case 'critical':
      return 'danger'
    case 'warning':
      return 'warning'
    default:
      return 'success'
  }
}

function riskLevelLabel(level: string): string {
  switch (level) {
    case 'critical':
      return '熔断'
    case 'warning':
      return '预警'
    default:
      return '正常'
  }
}

async function handleResumeSending() {
  resuming.value = true
  try {
    const res = await resumeSending()
    if (res.code === 200) {
      ElMessage.success('发送已恢复')
      await fetchRiskStatus()
    }
  } catch (e) {
    ElMessage.error('恢复失败')
  } finally {
    resuming.value = false
  }
}

function apiTypeLabel(key: string): string {
  const labels: Record<string, string> = {
    comment_api: '评论接口',
    video_api: '作品接口',
  }
  return labels[key] || key
}

function getQuotaColor(rate: number): string {
  if (rate >= 100) return '#f56c6c'
  if (rate >= 90) return '#e6a23c'
  return '#67c23a'
}

async function handleExport() {
  exporting.value = true
  try {
    const response = await exportLeads()
    const blob = new Blob([response.data], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `leads_export_${new Date().toISOString().slice(0, 10)}.xlsx`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch (e) {
    ElMessage.error('导出失败')
  } finally {
    exporting.value = false
  }
}

onMounted(() => {
  fetchDashboard()
  fetchTrend()
  fetchSalesPerformance()
  fetchMonitorStats()
  fetchQuotas()
  fetchDmStats()
  fetchRiskStatus()
})
</script>

<style scoped lang="scss">
.dashboard-container {
  padding: 0;
}

.page-title {
  margin: 0 0 20px;
  font-size: 20px;
  font-weight: 600;
  color: #303133;
}

.stat-cards {
  margin-bottom: 20px;
}

.stat-card {
  margin-bottom: 12px;

  &__body {
    display: flex;
    align-items: center;
    gap: 16px;
  }

  &__icon {
    width: 56px;
    height: 56px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }

  &__info {
    flex: 1;
    min-width: 0;
  }

  &__label {
    font-size: 13px;
    color: #909399;
    margin-bottom: 4px;
  }

  &__value {
    font-size: 28px;
    font-weight: 700;
    line-height: 1.2;
  }

  &--primary {
    .stat-card__icon {
      background: rgba(64, 158, 255, 0.1);
      color: #409eff;
    }
    .stat-card__value {
      color: #409eff;
    }
  }

  &--warning {
    .stat-card__icon {
      background: rgba(230, 162, 60, 0.1);
      color: #e6a23c;
    }
    .stat-card__value {
      color: #e6a23c;
    }
  }

  &--success {
    .stat-card__icon {
      background: rgba(103, 194, 58, 0.1);
      color: #67c23a;
    }
    .stat-card__value {
      color: #67c23a;
    }
  }

  &--danger {
    .stat-card__icon {
      background: rgba(245, 108, 108, 0.1);
      color: #f56c6c;
    }
    .stat-card__value {
      color: #f56c6c;
    }
  }

  &--info {
    .stat-card__icon {
      background: rgba(144, 147, 153, 0.1);
      color: #909399;
    }
    .stat-card__value {
      color: #606266;
    }
  }

  &__limit {
    font-size: 14px;
    font-weight: 400;
    color: #909399;
  }
}

.section-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
}

.chart-wrapper {
  width: 100%;
}

.date-filter {
  display: flex;
  align-items: center;
}

.export-section {
  margin-top: 10px;
  margin-bottom: 40px;
  text-align: right;
}

.quota-item {
  margin-bottom: 20px;
  padding: 0 8px;

  &__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 8px;
  }

  &__label {
    font-size: 14px;
    font-weight: 500;
    color: #303133;
  }

  &__count {
    font-size: 14px;
    color: #909399;
  }
}

.risk-card {
  border-left: 4px solid #67c23a;

  &--warning {
    border-left-color: #e6a23c;
  }

  &--critical {
    border-left-color: #f56c6c;
  }
}

.risk-stat {
  text-align: center;
  padding: 8px 0;

  &__label {
    font-size: 13px;
    color: #909399;
    margin-bottom: 6px;
  }

  &__value {
    font-size: 24px;
    font-weight: 700;
    color: #303133;

    &--danger {
      color: #f56c6c;
    }
  }
}

.risk-alert {
  margin-top: 16px;
}
</style>
