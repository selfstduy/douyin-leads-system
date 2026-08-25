<template>
  <div class="alert-list-container">
    <h2 class="page-title">告警中心</h2>

    <!-- 筛选栏 -->
    <el-card class="filter-card" shadow="never">
      <el-row :gutter="16">
        <el-col :span="6">
          <el-select v-model="filterLevel" placeholder="告警级别" clearable @change="fetchAlerts">
            <el-option label="全部" value="" />
            <el-option label="严重 (critical)" value="critical" />
            <el-option label="警告 (warning)" value="warning" />
            <el-option label="信息 (info)" value="info" />
          </el-select>
        </el-col>
        <el-col :span="6">
          <el-checkbox v-model="filterUnreadOnly" @change="fetchAlerts">仅看未读</el-checkbox>
        </el-col>
        <el-col :span="12" style="text-align: right">
          <el-button type="primary" :icon="Check" @click="handleMarkAllRead" :disabled="unreadCount === 0">
            全部标记已读
          </el-button>
        </el-col>
      </el-row>
    </el-card>

    <!-- 告警列表 -->
    <el-card shadow="never" class="table-card">
      <el-table :data="alerts" stripe style="width: 100%" v-loading="loading">
        <el-table-column label="级别" width="100">
          <template #default="{ row }">
            <el-tag :type="levelTagType(row.level)" size="small">
              {{ levelLabel(row.level) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
        <el-table-column prop="source" label="来源" width="100">
          <template #default="{ row }">
            {{ sourceLabel(row.source) }}
          </template>
        </el-table-column>
        <el-table-column prop="content" label="内容" min-width="250" show-overflow-tooltip />
        <el-table-column label="时间" width="170">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag v-if="row.is_read" type="info" size="small">已读</el-tag>
            <el-tag v-else type="danger" size="small">未读</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button v-if="!row.is_read" link type="primary" size="small" @click="handleMarkRead(row.id)">
              标记已读
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @size-change="fetchAlerts"
          @current-change="fetchAlerts"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Check } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { getAlerts, markAlertRead, markAllAlertsRead, getUnreadAlertCount } from '@/api/system'

const alerts = ref<any[]>([])
const loading = ref(false)
const currentPage = ref(1)
const pageSize = ref(20)
const total = ref(0)
const filterLevel = ref('')
const filterUnreadOnly = ref(false)
const unreadCount = ref(0)

async function fetchAlerts() {
  loading.value = true
  try {
    const params: any = {
      page: currentPage.value,
      page_size: pageSize.value,
    }
    if (filterLevel.value) params.level = filterLevel.value
    if (filterUnreadOnly.value) params.unread_only = true

    const res = await getAlerts(params)
    alerts.value = res.data || []
    total.value = res.total || 0
  } catch (e) {
    console.error('Failed to fetch alerts', e)
  } finally {
    loading.value = false
  }
}

async function fetchUnreadCount() {
  try {
    const res = await getUnreadAlertCount()
    if (res.code === 200) {
      unreadCount.value = res.data.unread_count || 0
    }
  } catch (e) {
    console.error('Failed to fetch unread count', e)
  }
}

async function handleMarkRead(id: number) {
  try {
    await markAlertRead(id)
    ElMessage.success('已标记已读')
    await fetchAlerts()
    await fetchUnreadCount()
  } catch (e) {
    ElMessage.error('操作失败')
  }
}

async function handleMarkAllRead() {
  try {
    await markAllAlertsRead()
    ElMessage.success('全部已标记已读')
    await fetchAlerts()
    await fetchUnreadCount()
  } catch (e) {
    ElMessage.error('操作失败')
  }
}

function levelTagType(level: string): string {
  switch (level) {
    case 'critical': return 'danger'
    case 'warning': return 'warning'
    default: return 'info'
  }
}

function levelLabel(level: string): string {
  switch (level) {
    case 'critical': return '严重'
    case 'warning': return '警告'
    case 'info': return '信息'
    default: return level
  }
}

function sourceLabel(source: string): string {
  const labels: Record<string, string> = {
    quota: '配额',
    crawler: '采集',
    report: '举报',
    system: '系统',
  }
  return labels[source] || source
}

function formatTime(iso: string): string {
  if (!iso) return '-'
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', { hour12: false })
}

onMounted(() => {
  fetchAlerts()
  fetchUnreadCount()
})
</script>

<style scoped lang="scss">
.alert-list-container {
  padding: 0;
}

.page-title {
  margin: 0 0 20px;
  font-size: 20px;
  font-weight: 600;
  color: #303133;
}

.filter-card {
  margin-bottom: 16px;
  border: none;

  :deep(.el-card__body) {
    padding: 16px 20px;
  }
}

.table-card {
  border: none;
}

.pagination-wrapper {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>
