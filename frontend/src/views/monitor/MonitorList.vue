<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">监控管理</h2>
    </div>

    <el-tabs v-model="activeTab" @tab-change="handleTabChange">
      <!-- Tab 1: 账号监控 -->
      <el-tab-pane label="账号监控" name="account">
        <el-card>
          <template #header>
            <div class="flex-between">
              <div class="toolbar">
                <el-input
                  v-model="searchText"
                  placeholder="搜索昵称/UID"
                  clearable
                  style="width: 200px"
                  @clear="handleSearch"
                  @keyup.enter="handleSearch"
                >
                  <template #prefix>
                    <el-icon><Search /></el-icon>
                  </template>
                </el-input>
                <el-select
                  v-model="statusFilter"
                  placeholder="全部状态"
                  clearable
                  style="width: 140px"
                  @change="handleSearch"
                >
                  <el-option label="运行中" value="active" />
                  <el-option label="已暂停" value="paused" />
                  <el-option label="异常" value="error" />
                </el-select>
                <el-button type="primary" @click="handleSearch">搜索</el-button>
              </div>
              <div class="toolbar-right">
                <el-button type="warning" plain :loading="discoveryLoading" @click="handleRunDiscovery">
                  <el-icon style="margin-right: 4px"><Search /></el-icon>全网发现
                </el-button>
                <el-button type="danger" plain :loading="cleaningLoading" @click="handleRunCleaning">
                  <el-icon style="margin-right: 4px"><Delete /></el-icon>清洗低质
                </el-button>
                <el-upload
                  ref="uploadRef"
                  :show-file-list="false"
                  accept=".csv,.xlsx,.xls"
                  :before-upload="handleBeforeUpload"
                  :http-request="handleBatchImport"
                >
                  <el-button :loading="importLoading">
                    <el-icon style="margin-right: 4px"><Upload /></el-icon>批量导入
                  </el-button>
                </el-upload>
                <el-button type="primary" @click="openCreateDialog">
                  <el-icon style="margin-right: 4px"><Plus /></el-icon>新增监控
                </el-button>
              </div>
            </div>
          </template>

          <el-table :data="monitorList" stripe v-loading="tableLoading" style="width: 100%">
            <el-table-column prop="nickname" label="昵称" min-width="120">
              <template #default="{ row }">
                {{ row.nickname || '-' }}
              </template>
            </el-table-column>
            <el-table-column prop="douyin_uid" label="抖音UID" min-width="160" show-overflow-tooltip />
            <el-table-column prop="douyin_url" label="链接" min-width="200" show-overflow-tooltip />
            <el-table-column prop="status" label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="statusTagType(row.status)">
                  {{ statusLabel(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="source" label="来源" width="100">
              <template #default="{ row }">
                <el-tag :type="row.source === 'discovered' ? 'success' : 'info'" size="small">
                  {{ row.source === 'discovered' ? '发现' : '手动' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="total_high_count" label="High数" width="80">
              <template #default="{ row }">
                {{ row.total_high_count || 0 }}
              </template>
            </el-table-column>
            <el-table-column prop="poll_interval_min" label="拉取间隔" width="100">
              <template #default="{ row }">
                {{ row.poll_interval_min }} 分钟
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="创建时间" width="180">
              <template #default="{ row }">
                {{ formatDate(row.created_at) }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="240" fixed="right">
              <template #default="{ row }">
                <el-switch
                  v-model="row.status"
                  active-value="active"
                  inactive-value="paused"
                  :loading="row._toggleLoading"
                  @change="handleToggle(row)"
                  :disabled="row.status === 'deleted'"
                  style="margin-right: 12px"
                />
                <el-button type="primary" link @click="openEditDialog(row)">编辑</el-button>
                <el-button type="danger" link @click="handleDelete(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>

          <div class="pagination-wrapper">
            <el-pagination
              v-model:current-page="pagination.page"
              v-model:page-size="pagination.pageSize"
              :total="pagination.total"
              :page-sizes="[10, 20, 50]"
              layout="total, sizes, prev, pager, next, jumper"
              @size-change="fetchMonitors"
              @current-change="fetchMonitors"
            />
          </div>
        </el-card>
      </el-tab-pane>

      <!-- Tab 2: 全网监控（话题监控） -->
      <el-tab-pane label="全网监控" name="topic">
        <el-card>
          <template #header>
            <div class="flex-between">
              <div class="toolbar">
                <el-input
                  v-model="topicSearchText"
                  placeholder="搜索话题"
                  clearable
                  style="width: 200px"
                  @clear="handleTopicSearch"
                  @keyup.enter="handleTopicSearch"
                >
                  <template #prefix>
                    <el-icon><Search /></el-icon>
                  </template>
                </el-input>
                <el-select
                  v-model="topicStatusFilter"
                  placeholder="全部状态"
                  clearable
                  style="width: 140px"
                  @change="handleTopicSearch"
                >
                  <el-option label="运行中" value="active" />
                  <el-option label="已暂停" value="paused" />
                </el-select>
                <el-button type="primary" @click="handleTopicSearch">搜索</el-button>
              </div>
              <div class="toolbar-right">
                <el-button type="primary" @click="openTopicCreateDialog">
                  <el-icon style="margin-right: 4px"><Plus /></el-icon>新增话题
                </el-button>
              </div>
            </div>
          </template>

          <el-table :data="topicMonitorList" stripe v-loading="topicTableLoading" style="width: 100%">
            <el-table-column prop="topic" label="话题" min-width="160" show-overflow-tooltip />
            <el-table-column prop="industry" label="行业" width="120">
              <template #default="{ row }">
                {{ row.industry || '-' }}
              </template>
            </el-table-column>
            <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip>
              <template #default="{ row }">
                {{ row.description || '-' }}
              </template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="statusTagType(row.status)">
                  {{ statusLabel(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="poll_interval_min" label="拉取间隔" width="100">
              <template #default="{ row }">
                {{ row.poll_interval_min }} 分钟
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="创建时间" width="180">
              <template #default="{ row }">
                {{ formatDate(row.created_at) }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="240" fixed="right">
              <template #default="{ row }">
                <el-switch
                  v-model="row.status"
                  active-value="active"
                  inactive-value="paused"
                  :loading="row._toggleLoading"
                  @change="handleTopicToggle(row)"
                  style="margin-right: 12px"
                />
                <el-button type="primary" link @click="openTopicEditDialog(row)">编辑</el-button>
                <el-button type="danger" link @click="handleTopicDelete(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>

          <div class="pagination-wrapper">
            <el-pagination
              v-model:current-page="topicPagination.page"
              v-model:page-size="topicPagination.pageSize"
              :total="topicPagination.total"
              :page-sizes="[10, 20, 50]"
              layout="total, sizes, prev, pager, next, jumper"
              @size-change="fetchTopicMonitors"
              @current-change="fetchTopicMonitors"
            />
          </div>
        </el-card>
      </el-tab-pane>

      <!-- Tab 3: 已移出账号 -->
      <el-tab-pane label="已移出账号" name="removed">
        <el-card>
          <template #header>
            <div class="flex-between">
              <div class="toolbar">
                <el-input
                  v-model="removedSearchText"
                  placeholder="搜索昵称/UID"
                  clearable
                  style="width: 200px"
                  @clear="handleRemovedSearch"
                  @keyup.enter="handleRemovedSearch"
                >
                  <template #prefix>
                    <el-icon><Search /></el-icon>
                  </template>
                </el-input>
                <el-button type="primary" @click="handleRemovedSearch">搜索</el-button>
              </div>
              <div class="toolbar-right">
                <el-button @click="fetchRemovedMonitors">刷新</el-button>
              </div>
            </div>
          </template>

          <el-table :data="removedList" stripe v-loading="removedTableLoading" style="width: 100%">
            <el-table-column prop="nickname" label="昵称" min-width="120">
              <template #default="{ row }">
                {{ row.nickname || '-' }}
              </template>
            </el-table-column>
            <el-table-column prop="douyin_uid" label="抖音UID" min-width="160" show-overflow-tooltip />
            <el-table-column prop="source" label="来源" width="100">
              <template #default="{ row }">
                <el-tag :type="row.source === 'discovered' ? 'success' : 'info'" size="small">
                  {{ row.source === 'discovered' ? '发现' : '手动' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="total_high_count" label="High数" width="80">
              <template #default="{ row }">
                {{ row.total_high_count || 0 }}
              </template>
            </el-table-column>
            <el-table-column prop="last_high_intent_at" label="最后High时间" width="180">
              <template #default="{ row }">
                {{ row.last_high_intent_at ? formatDate(row.last_high_intent_at) : '从未' }}
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="创建时间" width="180">
              <template #default="{ row }">
                {{ formatDate(row.created_at) }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="120" fixed="right">
              <template #default="{ row }">
                <el-button type="primary" link @click="handleRestore(row)">恢复</el-button>
              </template>
            </el-table-column>
          </el-table>

          <div class="pagination-wrapper">
            <el-pagination
              v-model:current-page="removedPagination.page"
              v-model:page-size="removedPagination.pageSize"
              :total="removedPagination.total"
              :page-sizes="[10, 20, 50]"
              layout="total, sizes, prev, pager, next, jumper"
              @size-change="fetchRemovedMonitors"
              @current-change="fetchRemovedMonitors"
            />
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <!-- ===== 账号监控弹窗 ===== -->

    <!-- Create Dialog -->
    <el-dialog v-model="createDialogVisible" title="新增监控" width="500px" destroy-on-close>
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-width="100px">
        <el-form-item label="抖音链接" prop="douyin_url">
          <el-input v-model="createForm.douyin_url" placeholder="输入抖音用户链接或UID" />
        </el-form-item>
        <el-form-item label="拉取间隔" prop="poll_interval_min">
          <el-input-number v-model="createForm.poll_interval_min" :min="1" :max="1440" />
          <span style="margin-left: 8px; color: #909399">分钟</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleCreate">确定</el-button>
      </template>
    </el-dialog>

    <!-- Edit Dialog -->
    <el-dialog v-model="editDialogVisible" title="编辑监控" width="500px" destroy-on-close>
      <el-form ref="editFormRef" :model="editForm" label-width="100px">
        <el-form-item label="昵称">
          <el-input v-model="editForm.nickname" placeholder="请输入昵称" />
        </el-form-item>
        <el-form-item label="拉取间隔">
          <el-input-number v-model="editForm.poll_interval_min" :min="1" :max="1440" />
          <span style="margin-left: 8px; color: #909399">分钟</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleEdit">确定</el-button>
      </template>
    </el-dialog>

    <!-- ===== 全网监控（话题监控）弹窗 ===== -->

    <!-- Create Topic Dialog -->
    <el-dialog v-model="topicCreateDialogVisible" title="新增话题监控" width="500px" destroy-on-close>
      <el-form ref="topicCreateFormRef" :model="topicCreateForm" :rules="topicCreateRules" label-width="100px">
        <el-form-item label="话题/行业" prop="topic">
          <el-input v-model="topicCreateForm.topic" placeholder="输入监控话题，如"情感挽回"、"心理咨询"" />
        </el-form-item>
        <el-form-item label="行业分类" prop="industry">
          <el-select v-model="topicCreateForm.industry" placeholder="请选择行业（可选）" clearable allow-create filterable style="width: 100%">
            <el-option label="情感咨询" value="情感咨询" />
            <el-option label="心理健康" value="心理健康" />
            <el-option label="教育培训" value="教育培训" />
            <el-option label="医美整形" value="医美整形" />
            <el-option label="法律咨询" value="法律咨询" />
            <el-option label="金融理财" value="金融理财" />
          </el-select>
        </el-form-item>
        <el-form-item label="话题描述" prop="description">
          <el-input
            v-model="topicCreateForm.description"
            type="textarea"
            :rows="3"
            placeholder="可选，帮助舆情API理解采集范围，如：关注情感挽回、恋爱技巧、婚姻修复等方向"
          />
        </el-form-item>
        <el-form-item label="拉取间隔" prop="poll_interval_min">
          <el-input-number v-model="topicCreateForm.poll_interval_min" :min="1" :max="1440" />
          <span style="margin-left: 8px; color: #909399">分钟</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="topicCreateDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="topicSubmitLoading" @click="handleTopicCreate">确定</el-button>
      </template>
    </el-dialog>

    <!-- Edit Topic Dialog -->
    <el-dialog v-model="topicEditDialogVisible" title="编辑话题监控" width="500px" destroy-on-close>
      <el-form ref="topicEditFormRef" :model="topicEditForm" label-width="100px">
        <el-form-item label="话题/行业">
          <el-input v-model="topicEditForm.topic" placeholder="输入监控话题" />
        </el-form-item>
        <el-form-item label="行业分类">
          <el-select v-model="topicEditForm.industry" placeholder="请选择行业（可选）" clearable allow-create filterable style="width: 100%">
            <el-option label="情感咨询" value="情感咨询" />
            <el-option label="心理健康" value="心理健康" />
            <el-option label="教育培训" value="教育培训" />
            <el-option label="医美整形" value="医美整形" />
            <el-option label="法律咨询" value="法律咨询" />
            <el-option label="金融理财" value="金融理财" />
          </el-select>
        </el-form-item>
        <el-form-item label="话题描述">
          <el-input
            v-model="topicEditForm.description"
            type="textarea"
            :rows="3"
            placeholder="可选，帮助舆情API理解采集范围"
          />
        </el-form-item>
        <el-form-item label="拉取间隔">
          <el-input-number v-model="topicEditForm.poll_interval_min" :min="1" :max="1440" />
          <span style="margin-left: 8px; color: #909399">分钟</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="topicEditDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="topicSubmitLoading" @click="handleTopicEdit">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UploadRequestOptions, UploadInstance } from 'element-plus'
import { Search, Plus, Upload, Delete } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import {
  getMonitors, createMonitor, updateMonitor, deleteMonitor,
  toggleMonitor, batchImport, runDiscovery, runCleaning,
  getRemovedMonitors, restoreMonitor,
} from '@/api/monitor'
import type { MonitorItem } from '@/api/monitor'
import {
  getTopicMonitors, createTopicMonitor, updateTopicMonitor,
  deleteTopicMonitor, toggleTopicMonitor,
} from '@/api/topicMonitor'
import type { TopicMonitorItem } from '@/api/topicMonitor'

// ── Tab state ──
const activeTab = ref('account')

function handleTabChange(tab: string | number) {
  if (tab === 'account') {
    fetchMonitors()
  } else if (tab === 'topic') {
    fetchTopicMonitors()
  } else if (tab === 'removed') {
    fetchRemovedMonitors()
  }
}

// ── 通用工具函数 ──
function formatDate(dateStr: string) {
  if (!dateStr) return ''
  return new Date(dateStr).toLocaleString('zh-CN')
}

function statusTagType(status: string) {
  const map: Record<string, string> = { active: 'success', paused: 'warning', deleted: 'danger', error: 'danger', removed: 'info' }
  return map[status] || 'info'
}

function statusLabel(status: string) {
  const map: Record<string, string> = { active: '运行中', paused: '已暂停', deleted: '已删除', error: '异常', removed: '已移出' }
  return map[status] || status
}

// ═══════════════════════════════════════════════════════════════
//  账号监控
// ═══════════════════════════════════════════════════════════════

const monitorList = ref<(MonitorItem & { _toggleLoading?: boolean })[]>([])
const tableLoading = ref(false)
const searchText = ref('')
const statusFilter = ref('')
const pagination = reactive({ page: 1, pageSize: 20, total: 0 })

async function fetchMonitors() {
  tableLoading.value = true
  try {
    const res: any = await getMonitors({
      page: pagination.page,
      page_size: pagination.pageSize,
      status: statusFilter.value || undefined,
      search: searchText.value || undefined,
    })
    if (res.code === 200) {
      monitorList.value = (res.data || []).map((item: MonitorItem) => ({ ...item, _toggleLoading: false }))
      pagination.total = res.total
    }
  } finally {
    tableLoading.value = false
  }
}

function handleSearch() {
  pagination.page = 1
  fetchMonitors()
}

// ── Create dialog ──
const createDialogVisible = ref(false)
const createFormRef = ref<FormInstance>()
const submitLoading = ref(false)

const createForm = reactive({ douyin_url: '', poll_interval_min: 5 })
const createRules: FormRules = {
  douyin_url: [{ required: true, message: '请输入抖音链接或UID', trigger: 'blur' }],
  poll_interval_min: [{ required: true, message: '请输入拉取间隔', trigger: 'blur' }],
}

function openCreateDialog() {
  createForm.douyin_url = ''
  createForm.poll_interval_min = 5
  createDialogVisible.value = true
}

async function handleCreate() {
  if (!createFormRef.value) return
  const valid = await createFormRef.value.validate().catch(() => false)
  if (!valid) return
  submitLoading.value = true
  try {
    const res: any = await createMonitor(createForm)
    if (res.code === 200) {
      ElMessage.success('监控创建成功')
      createDialogVisible.value = false
      fetchMonitors()
    } else {
      ElMessage.error(res.message || '创建失败')
    }
  } finally {
    submitLoading.value = false
  }
}

// ── Edit dialog ──
const editDialogVisible = ref(false)
const editFormRef = ref<FormInstance>()
const editForm = reactive({ id: 0, nickname: '', poll_interval_min: 5 })

function openEditDialog(row: MonitorItem) {
  editForm.id = row.id
  editForm.nickname = row.nickname
  editForm.poll_interval_min = row.poll_interval_min
  editDialogVisible.value = true
}

async function handleEdit() {
  submitLoading.value = true
  try {
    const res: any = await updateMonitor(editForm.id, {
      nickname: editForm.nickname,
      poll_interval_min: editForm.poll_interval_min,
    })
    if (res.code === 200) {
      ElMessage.success('更新成功')
      editDialogVisible.value = false
      fetchMonitors()
    } else {
      ElMessage.error(res.message || '更新失败')
    }
  } finally {
    submitLoading.value = false
  }
}

// ── Toggle ──
async function handleToggle(row: MonitorItem & { _toggleLoading?: boolean }) {
  row._toggleLoading = true
  try {
    const res: any = await toggleMonitor(row.id)
    if (res.code === 200) {
      ElMessage.success(res.data?.status === 'active' ? '已启动' : '已暂停')
      fetchMonitors()
    } else {
      ElMessage.error(res.message || '操作失败')
      fetchMonitors()
    }
  } catch {
    fetchMonitors()
  } finally {
    row._toggleLoading = false
  }
}

// ── Delete ──
async function handleDelete(row: MonitorItem) {
  try {
    await ElMessageBox.confirm(`确定要删除该监控账号吗？`, '删除确认', {
      type: 'warning',
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  submitLoading.value = true
  try {
    const res: any = await deleteMonitor(row.id)
    if (res.code === 200) {
      ElMessage.success('删除成功')
      fetchMonitors()
    } else {
      ElMessage.error(res.message || '删除失败')
    }
  } finally {
    submitLoading.value = false
  }
}

// ── Batch import ──
const uploadRef = ref<UploadInstance>()
const importLoading = ref(false)

function handleBeforeUpload(file: File) {
  const allowed = ['.csv', '.xlsx', '.xls']
  const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase()
  if (!allowed.includes(ext)) {
    ElMessage.error('仅支持 .csv 和 .xlsx 格式')
    return false
  }
  return true
}

async function handleBatchImport(options: UploadRequestOptions) {
  importLoading.value = true
  try {
    const res: any = await batchImport(options.file)
    if (res.code === 200) {
      ElMessage.success(res.message || '导入完成')
      fetchMonitors()
    } else {
      ElMessage.error(res.message || '导入失败')
    }
  } catch {
    ElMessage.error('导入失败')
  } finally {
    importLoading.value = false
  }
}

// ── 全网发现 & 清洗 ──
const discoveryLoading = ref(false)
const cleaningLoading = ref(false)

async function handleRunDiscovery() {
  try {
    await ElMessageBox.confirm(
      '全网发现是高成本操作，将在后台异步执行。确认开始？',
      '全网发现',
      { type: 'warning', confirmButtonText: '开始', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  discoveryLoading.value = true
  try {
    const res: any = await runDiscovery()
    if (res.code === 200) {
      ElMessage.success(res.message || '全网发现任务已提交')
    } else {
      ElMessage.error(res.message || '提交失败')
    }
  } catch {
    ElMessage.error('提交失败')
  } finally {
    discoveryLoading.value = false
  }
}

async function handleRunCleaning() {
  try {
    await ElMessageBox.confirm(
      '将清洗超过14天无high评论的账号，此操作可恢复。确认执行？',
      '账号清洗',
      { type: 'warning', confirmButtonText: '执行', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  cleaningLoading.value = true
  try {
    const res: any = await runCleaning()
    if (res.code === 200) {
      ElMessage.success(res.message || '清洗任务已提交')
    } else {
      ElMessage.error(res.message || '提交失败')
    }
  } catch {
    ElMessage.error('提交失败')
  } finally {
    cleaningLoading.value = false
  }
}

// ═══════════════════════════════════════════════════════════════
//  全网监控（话题监控）
// ═══════════════════════════════════════════════════════════════

const topicMonitorList = ref<(TopicMonitorItem & { _toggleLoading?: boolean })[]>([])
const topicTableLoading = ref(false)
const topicSearchText = ref('')
const topicStatusFilter = ref('')
const topicPagination = reactive({ page: 1, pageSize: 20, total: 0 })

async function fetchTopicMonitors() {
  topicTableLoading.value = true
  try {
    const res: any = await getTopicMonitors({
      page: topicPagination.page,
      page_size: topicPagination.pageSize,
      status: topicStatusFilter.value || undefined,
      search: topicSearchText.value || undefined,
    })
    if (res.code === 200) {
      topicMonitorList.value = (res.data || []).map((item: TopicMonitorItem) => ({ ...item, _toggleLoading: false }))
      topicPagination.total = res.total
    }
  } finally {
    topicTableLoading.value = false
  }
}

function handleTopicSearch() {
  topicPagination.page = 1
  fetchTopicMonitors()
}

// ── Create Topic dialog ──
const topicCreateDialogVisible = ref(false)
const topicCreateFormRef = ref<FormInstance>()
const topicSubmitLoading = ref(false)

const topicCreateForm = reactive({ topic: '', industry: '', description: '', poll_interval_min: 5 })
const topicCreateRules: FormRules = {
  topic: [{ required: true, message: '请输入监控话题/行业', trigger: 'blur' }],
}

function openTopicCreateDialog() {
  topicCreateForm.topic = ''
  topicCreateForm.industry = ''
  topicCreateForm.description = ''
  topicCreateForm.poll_interval_min = 5
  topicCreateDialogVisible.value = true
}

async function handleTopicCreate() {
  if (!topicCreateFormRef.value) return
  const valid = await topicCreateFormRef.value.validate().catch(() => false)
  if (!valid) return
  topicSubmitLoading.value = true
  try {
    const res: any = await createTopicMonitor(topicCreateForm)
    if (res.code === 200) {
      ElMessage.success('话题监控创建成功')
      topicCreateDialogVisible.value = false
      fetchTopicMonitors()
    } else {
      ElMessage.error(res.message || '创建失败')
    }
  } finally {
    topicSubmitLoading.value = false
  }
}

// ── Edit Topic dialog ──
const topicEditDialogVisible = ref(false)
const topicEditFormRef = ref<FormInstance>()
const topicEditForm = reactive({ id: 0, topic: '', industry: '', description: '', poll_interval_min: 5 })

function openTopicEditDialog(row: TopicMonitorItem) {
  topicEditForm.id = row.id
  topicEditForm.topic = row.topic
  topicEditForm.industry = row.industry
  topicEditForm.description = row.description
  topicEditForm.poll_interval_min = row.poll_interval_min
  topicEditDialogVisible.value = true
}

async function handleTopicEdit() {
  topicSubmitLoading.value = true
  try {
    const res: any = await updateTopicMonitor(topicEditForm.id, {
      topic: topicEditForm.topic,
      industry: topicEditForm.industry,
      description: topicEditForm.description,
      poll_interval_min: topicEditForm.poll_interval_min,
    })
    if (res.code === 200) {
      ElMessage.success('更新成功')
      topicEditDialogVisible.value = false
      fetchTopicMonitors()
    } else {
      ElMessage.error(res.message || '更新失败')
    }
  } finally {
    topicSubmitLoading.value = false
  }
}

// ── Topic Toggle ──
async function handleTopicToggle(row: TopicMonitorItem & { _toggleLoading?: boolean }) {
  row._toggleLoading = true
  try {
    const res: any = await toggleTopicMonitor(row.id)
    if (res.code === 200) {
      ElMessage.success(res.data?.status === 'active' ? '已启动' : '已暂停')
      fetchTopicMonitors()
    } else {
      ElMessage.error(res.message || '操作失败')
      fetchTopicMonitors()
    }
  } catch {
    fetchTopicMonitors()
  } finally {
    row._toggleLoading = false
  }
}

// ── Topic Delete ──
async function handleTopicDelete(row: TopicMonitorItem) {
  try {
    await ElMessageBox.confirm(`确定要删除话题监控"${row.topic}"吗？`, '删除确认', {
      type: 'warning',
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  topicSubmitLoading.value = true
  try {
    const res: any = await deleteTopicMonitor(row.id)
    if (res.code === 200) {
      ElMessage.success('删除成功')
      fetchTopicMonitors()
    } else {
      ElMessage.error(res.message || '删除失败')
    }
  } finally {
    topicSubmitLoading.value = false
  }
}

// ═══════════════════════════════════════════════════════════════
//  已移出账号
// ═══════════════════════════════════════════════════════════════

const removedList = ref<MonitorItem[]>([])
const removedTableLoading = ref(false)
const removedSearchText = ref('')
const removedPagination = reactive({ page: 1, pageSize: 20, total: 0 })

async function fetchRemovedMonitors() {
  removedTableLoading.value = true
  try {
    const res: any = await getRemovedMonitors({
      page: removedPagination.page,
      page_size: removedPagination.pageSize,
      search: removedSearchText.value || undefined,
    })
    if (res.code === 200) {
      removedList.value = res.data || []
      removedPagination.total = res.total
    }
  } finally {
    removedTableLoading.value = false
  }
}

function handleRemovedSearch() {
  removedPagination.page = 1
  fetchRemovedMonitors()
}

async function handleRestore(row: MonitorItem) {
  try {
    await ElMessageBox.confirm(
      `确认恢复账号 "${row.nickname || row.douyin_uid}" 到监控池？`,
      '恢复确认',
      { type: 'info', confirmButtonText: '恢复', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    const res: any = await restoreMonitor(row.id)
    if (res.code === 200) {
      ElMessage.success('账号已恢复')
      fetchRemovedMonitors()
    } else {
      ElMessage.error(res.message || '恢复失败')
    }
  } catch {
    ElMessage.error('恢复失败')
  }
}

// ── Init ──
onMounted(() => {
  fetchMonitors()
})
</script>

<style scoped lang="scss">
.page-container {
  padding: 0;
}

.page-header {
  margin-bottom: 16px;
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

.flex-between {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
