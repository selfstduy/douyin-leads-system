<template>
  <div class="config-management">
    <h2 class="page-title">系统参数配置</h2>

    <!-- 分类Tab -->
    <el-card shadow="never" class="config-card">
      <el-tabs v-model="activeCategory" @tab-click="handleTabChange">
        <el-tab-pane
          v-for="cat in categories"
          :key="cat.value"
          :label="cat.label"
          :name="cat.value"
        >
          <el-form
            v-if="groupedConfigs[cat.value]"
            label-width="220px"
            label-position="right"
            class="config-form"
          >
            <el-form-item
              v-for="item in groupedConfigs[cat.value]"
              :key="item.key"
              :label="item.label"
            >
              <div class="config-item">
                <!-- 数值类型 -->
                <el-input-number
                  v-if="item.value_type === 'int'"
                  v-model.number="editValues[item.key]"
                  :min="0"
                  controls-position="right"
                  style="width: 200px"
                />
                <!-- 浮点型 -->
                <el-input
                  v-else-if="item.value_type === 'float'"
                  v-model="editValues[item.key]"
                  style="width: 200px"
                  placeholder="输入浮点数"
                />
                <!-- 布尔型 -->
                <el-switch
                  v-else-if="item.value_type === 'bool'"
                  v-model="editValues[item.key]"
                  active-value="true"
                  inactive-value="false"
                />
                <!-- JSON -->
                <el-input
                  v-else-if="item.value_type === 'json'"
                  v-model="editValues[item.key]"
                  type="textarea"
                  :rows="2"
                  style="width: 400px"
                />
                <!-- 字符串 -->
                <el-input
                  v-else
                  v-model="editValues[item.key]"
                  style="width: 300px"
                  placeholder="输入配置值"
                />

                <!-- 保存按钮 -->
                <el-button
                  type="primary"
                  size="small"
                  :loading="savingKeys[item.key]"
                  :disabled="editValues[item.key] === item.value"
                  @click="handleSave(item)"
                  style="margin-left: 12px"
                >
                  保存
                </el-button>

                <!-- 说明 -->
                <span class="config-desc">{{ item.description }}</span>
              </div>
            </el-form-item>
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 变更日志 -->
    <el-card shadow="never" class="log-card">
      <template #header>
        <div class="log-header">
          <span class="log-title">变更日志</span>
          <el-input
            v-model="logFilterKey"
            placeholder="按配置项key筛选"
            clearable
            style="width: 250px"
            @clear="fetchLogs"
            @keyup.enter="fetchLogs"
          >
            <template #append>
              <el-button @click="fetchLogs">搜索</el-button>
            </template>
          </el-input>
        </div>
      </template>

      <el-table :data="logs" stripe style="width: 100%" v-loading="logsLoading">
        <el-table-column prop="config_key" label="配置项" min-width="180" show-overflow-tooltip />
        <el-table-column prop="old_value" label="旧值" width="150" show-overflow-tooltip>
          <template #default="{ row }">
            <el-tag type="info" size="small">{{ row.old_value || '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="new_value" label="新值" width="150" show-overflow-tooltip>
          <template #default="{ row }">
            <el-tag type="success" size="small">{{ row.new_value }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="changed_by" label="操作人" width="120" />
        <el-table-column label="时间" width="170">
          <template #default="{ row }">
            {{ formatTime(row.changed_at) }}
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="logPage"
          v-model:page-size="logPageSize"
          :total="logTotal"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @size-change="fetchLogs"
          @current-change="fetchLogs"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import type { TabsPaneContext } from 'element-plus'
import { getSystemConfigs, updateSystemConfig, getConfigChangeLogs } from '@/api/system'

// ── 分类定义 ──
const categories = [
  { value: 'quota', label: '配额管理' },
  { value: 'dm', label: '私信配置' },
  { value: 'risk', label: '风控参数' },
  { value: 'crawler', label: '采集配置' },
  { value: 'discovery', label: '发现配置' },
  { value: 'ai', label: 'AI配置' },
]

const activeCategory = ref('quota')
const configs = ref<any[]>([])
const editValues = reactive<Record<string, string>>({})
const savingKeys = reactive<Record<string, boolean>>({})

// ── 变更日志 ──
const logs = ref<any[]>([])
const logsLoading = ref(false)
const logPage = ref(1)
const logPageSize = ref(20)
const logTotal = ref(0)
const logFilterKey = ref('')

// ── 按分类分组 ──
const groupedConfigs = computed(() => {
  const groups: Record<string, any[]> = {}
  for (const c of configs.value) {
    if (!groups[c.category]) groups[c.category] = []
    groups[c.category].push(c)
  }
  return groups
})

// ── 加载配置 ──
async function fetchConfigs() {
  try {
    const res = await getSystemConfigs()
    if (res.code === 200) {
      configs.value = res.data || []
      // 初始化编辑值
      for (const c of configs.value) {
        editValues[c.key] = c.value
      }
    }
  } catch (e) {
    ElMessage.error('加载配置失败')
  }
}

// ── 保存单个配置 ──
async function handleSave(item: any) {
  const key = item.key
  const value = String(editValues[key])

  // 类型校验
  if (item.value_type === 'int' && isNaN(Number(value))) {
    ElMessage.error('请输入有效的整数')
    return
  }
  if (item.value_type === 'float' && isNaN(Number(value))) {
    ElMessage.error('请输入有效的数字')
    return
  }

  savingKeys[key] = true
  try {
    const res: any = await updateSystemConfig(key, value)
    if (res.code === 200) {
      ElMessage.success(`"${item.label}" 已保存`)
      // 更新本地数据
      item.value = value
      await fetchLogs()
    } else {
      ElMessage.error(res.message || '保存失败')
    }
  } catch (e: any) {
    const msg = e?.response?.data?.detail || '保存失败'
    ElMessage.error(msg)
  } finally {
    savingKeys[key] = false
  }
}

// ── 加载变更日志 ──
async function fetchLogs() {
  logsLoading.value = true
  try {
    const params: any = {
      page: logPage.value,
      page_size: logPageSize.value,
    }
    if (logFilterKey.value) params.key = logFilterKey.value

    const res: any = await getConfigChangeLogs(params)
    if (res.code === 200) {
      logs.value = res.data || []
      logTotal.value = res.total || 0
    }
  } catch (e) {
    ElMessage.error('加载变更日志失败')
  } finally {
    logsLoading.value = false
  }
}

function handleTabChange(_tab: TabsPaneContext) {
  // 切换tab时无额外操作，数据已加载
}

function formatTime(iso: string): string {
  if (!iso) return '-'
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', { hour12: false })
}

onMounted(() => {
  fetchConfigs()
  fetchLogs()
})
</script>

<style scoped lang="scss">
.config-management {
  padding: 0;
}

.page-title {
  margin: 0 0 20px;
  font-size: 20px;
  font-weight: 600;
  color: #303133;
}

.config-card {
  border: none;
  margin-bottom: 20px;

  :deep(.el-card__body) {
    padding: 16px 20px;
  }
}

.config-form {
  :deep(.el-form-item) {
    margin-bottom: 16px;
    border-bottom: 1px solid #f0f0f0;
    padding-bottom: 12px;

    &:last-child {
      border-bottom: none;
    }
  }

  :deep(.el-form-item__label) {
    font-weight: 500;
    color: #303133;
  }
}

.config-item {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.config-desc {
  color: #909399;
  font-size: 12px;
  margin-left: 8px;
}

.log-card {
  border: none;

  :deep(.el-card__header) {
    padding: 16px 20px;
    border-bottom: 1px solid #ebeef5;
  }
}

.log-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.log-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.pagination-wrapper {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>
