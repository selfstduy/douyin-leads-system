<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">线索管理</h2>
    </div>

    <!-- ── 筛选区 ──────────────────────────────────────────────────────────── -->
    <el-card class="filter-card">
      <div class="filter-row">
        <div class="filter-group">
          <span class="filter-label">意向等级:</span>
          <el-check-tag
            :checked="!filters.intent_level"
            @change="filters.intent_level = ''; handleSearch()"
          >全部</el-check-tag>
          <el-check-tag
            :checked="filters.intent_level === 'high'"
            @change="filters.intent_level = 'high'; handleSearch()"
          >高意向</el-check-tag>
          <el-check-tag
            :checked="filters.intent_level === 'medium'"
            @change="filters.intent_level = 'medium'; handleSearch()"
          >中意向</el-check-tag>
          <el-check-tag
            :checked="filters.intent_level === 'invalid'"
            @change="filters.intent_level = 'invalid'; handleSearch()"
          >无效</el-check-tag>
        </div>
        <div class="filter-group">
          <span class="filter-label">状态:</span>
          <el-select v-model="filters.status" placeholder="全部" clearable style="width: 130px" @change="handleSearch">
            <el-option label="待分配" value="pending" />
            <el-option label="已分配" value="assigned" />
            <el-option label="跟进中" value="following" />
            <el-option label="已转化" value="converted" />
            <el-option label="已关闭" value="closed" />
          </el-select>
        </div>
      </div>
      <div class="filter-row" style="margin-top: 12px">
        <div class="filter-group">
          <span class="filter-label">时间:</span>
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            value-format="YYYY-MM-DD"
            style="width: 260px"
            @change="handleSearch"
          />
        </div>
        <div class="filter-group">
          <el-input
            v-model="filters.search"
            placeholder="搜索用户昵称"
            clearable
            style="width: 180px"
            @clear="handleSearch"
            @keyup.enter="handleSearch"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
          <el-button type="primary" @click="handleSearch">搜索</el-button>
        </div>
        <div class="filter-actions" v-if="isAdmin">
          <el-button type="success" :loading="autoAssignLoading" @click="handleAutoAssign">
            <el-icon style="margin-right: 4px"><Connection /></el-icon>自动分配
          </el-button>
          <el-button type="warning" :disabled="selectedIds.length === 0" @click="openBatchAssignDialog">
            <el-icon style="margin-right: 4px"><Switch /></el-icon>批量分配
            <span v-if="selectedIds.length > 0" style="margin-left: 4px">({{ selectedIds.length }})</span>
          </el-button>
        </div>
      </div>
    </el-card>

    <!-- ── 线索表格 ──────────────────────────────────────────────────────────── -->
    <el-card style="margin-top: 12px">
      <el-table
        :data="leadList"
        stripe
        v-loading="tableLoading"
        style="width: 100%"
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="45" v-if="isAdmin" />
        <el-table-column prop="user_nickname" label="用户昵称" min-width="120" show-overflow-tooltip />
        <el-table-column prop="comment_content" label="评论内容" min-width="200" show-overflow-tooltip />
        <el-table-column prop="intent_level" label="意向等级" width="100">
          <template #default="{ row }">
            <el-tag :type="intentTagType(row.intent_level)" size="small">
              {{ intentLabel(row.intent_level) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="video_title" label="来源视频" min-width="160" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="chat_status" label="对话状态" width="100">
          <template #default="{ row }">
            <el-tag :type="chatStatusTagType(row.chat_status)" size="small">
              {{ chatStatusLabel(row.chat_status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="assigned_to_name" label="分配给" width="100">
          <template #default="{ row }">
            {{ row.assigned_to_name || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="170">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link @click="openDetail(row)">详情</el-button>
            <el-button v-if="isAdmin" type="warning" link @click="openAssignDialog(row)">分配</el-button>
            <el-button type="success" link @click="goChat(row)">聊天</el-button>
            <el-button
              v-if="row.chat_status === 2"
              type="danger"
              link
              @click="openTransferDialog(row)"
            >转人工</el-button>
            <el-button
              v-if="isAdmin && row.intent_level !== 'invalid'"
              type="info"
              link
              @click="handleMarkInvalid(row)"
            >标记无效</el-button>
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
          @size-change="fetchLeads"
          @current-change="fetchLeads"
        />
      </div>
    </el-card>

    <!-- ── 线索详情抽屉 ──────────────────────────────────────────────────────── -->
    <el-drawer v-model="drawerVisible" title="线索详情" size="560px" destroy-on-close>
      <template v-if="detailData">
        <!-- 用户信息 -->
        <div class="detail-section">
          <h4 class="section-title">用户信息</h4>
          <div class="user-info-row">
            <el-avatar :src="detailData.user_avatar" :size="48" />
            <div class="user-meta">
              <div class="user-nickname">{{ detailData.user_nickname }}</div>
              <div class="user-uid">UID: {{ detailData.user_uid }}</div>
            </div>
          </div>
        </div>

        <!-- 原始评论 -->
        <div class="detail-section">
          <h4 class="section-title">原始评论</h4>
          <div class="comment-box">{{ detailData.comment_content || '无评论内容' }}</div>
        </div>

        <!-- AI分析 -->
        <div class="detail-section">
          <h4 class="section-title">AI 分析</h4>
          <div class="ai-info">
            <div>
              意向等级:
              <el-tag :type="intentTagType(detailData.intent_level)" size="small">
                {{ intentLabel(detailData.intent_level) }}
              </el-tag>
            </div>
            <div class="ai-reason">{{ detailData.ai_reason || '暂无分析理由' }}</div>
          </div>
        </div>

        <!-- 来源 -->
        <div class="detail-section">
          <h4 class="section-title">来源信息</h4>
          <div class="source-info">
            <div>视频: {{ detailData.video_title || '-' }}</div>
            <div>监控账号: {{ detailData.monitor_account_name || '-' }}</div>
            <div>创建时间: {{ formatDate(detailData.created_at) }}</div>
          </div>
        </div>

        <!-- 状态 & 分配操作 -->
        <div class="detail-section">
          <h4 class="section-title">状态操作</h4>
          <div class="action-row">
            <el-select
              v-model="detailData.status"
              placeholder="当前状态"
              style="width: 140px"
              @change="handleStatusChange"
            >
              <el-option
                v-for="opt in statusOptions"
                :key="opt.value"
                :label="opt.label"
                :value="opt.value"
              />
            </el-select>
            <el-select
              v-if="isAdmin"
              v-model="detailAssignUser"
              placeholder="分配给..."
              clearable
              filterable
              style="width: 140px; margin-left: 8px"
              @change="handleDetailAssign"
            >
              <el-option
                v-for="u in salesUsers"
                :key="u.id"
                :label="u.username"
                :value="u.id"
              />
            </el-select>
          </div>
        </div>

        <!-- AI对话预览 -->
        <div class="detail-section" v-if="detailData.chat_status > 0">
          <h4 class="section-title">
            AI对话预览
            <el-tag
              v-if="detailData.chat_status === 2"
              type="warning"
              size="small"
              style="margin-left: 8px"
              effect="dark"
            >AI自动跟进中</el-tag>
            <el-tag v-else type="success" size="small" style="margin-left: 8px">人工服务</el-tag>
          </h4>
          <div v-if="recentMessages.length > 0" class="chat-preview-list">
            <div
              v-for="msg in recentMessages.slice(-5)"
              :key="msg.id"
              :class="['chat-preview-item', msg.direction]"
            >
              <span class="preview-direction">{{ msg.direction === 'outbound' ? (msg.is_ai ? 'AI' : '我方') : '用户' }}</span>
              <span class="preview-content">{{ msg.content }}</span>
            </div>
            <el-button
              type="primary"
              link
              size="small"
              style="margin-top: 8px"
              @click="goChat(detailData)"
            >查看完整对话 →</el-button>
          </div>
          <el-empty v-else description="暂无对话消息" :image-size="60" />
        </div>

        <!-- 跟进记录时间线 -->
        <div class="detail-section">
          <h4 class="section-title">跟进记录</h4>
          <el-timeline v-if="detailData.followups && detailData.followups.length > 0">
            <el-timeline-item
              v-for="f in detailData.followups"
              :key="f.id"
              :timestamp="formatDate(f.created_at)"
              placement="top"
              :type="followupTimelineType(f.action)"
            >
              <div class="followup-item">
                <span class="followup-operator">{{ f.operator_name }}</span>
                <el-tag size="small" :type="followupTimelineType(f.action)" style="margin: 0 6px">
                  {{ followupActionLabel(f.action) }}
                </el-tag>
                <span class="followup-content">{{ f.content }}</span>
              </div>
            </el-timeline-item>
          </el-timeline>
          <el-empty v-else description="暂无跟进记录" :image-size="60" />
        </div>

        <!-- 添加跟进备注 -->
        <div class="detail-section">
          <h4 class="section-title">添加备注</h4>
          <el-input
            v-model="followupContent"
            type="textarea"
            :rows="3"
            placeholder="输入跟进备注..."
          />
          <el-button
            type="primary"
            style="margin-top: 8px"
            :loading="followupLoading"
            :disabled="!followupContent.trim()"
            @click="handleAddFollowup"
          >
            提交备注
          </el-button>
        </div>

        <!-- 进入聊天 -->
        <div class="detail-section">
          <div class="chat-status-row">
            <span class="filter-label">对话状态:</span>
            <el-tag :type="chatStatusTagType(detailData.chat_status)" size="small">
              {{ chatStatusLabel(detailData.chat_status) }}
            </el-tag>
          </div>
          <el-button type="primary" style="width: 100%; margin-top: 8px" @click="goChat(detailData)">
            <el-icon style="margin-right: 4px"><ChatDotRound /></el-icon>进入聊天
          </el-button>
          <el-button
            v-if="detailData.chat_status === 2"
            type="warning"
            style="width: 100%; margin-top: 8px"
            @click="openTransferDialog(detailData)"
          >
            <el-icon style="margin-right: 4px"><Switch /></el-icon>转为人工服务
          </el-button>
        </div>
      </template>
    </el-drawer>

    <!-- ── 分配弹窗 ──────────────────────────────────────────────────────────── -->
    <el-dialog v-model="assignDialogVisible" :title="assignDialogTitle" width="420px" destroy-on-close>
      <el-form label-width="80px">
        <el-form-item label="销售人员">
          <el-select v-model="assignUserId" placeholder="选择销售人员" filterable style="width: 100%">
            <el-option
              v-for="u in salesUsers"
              :key="u.id"
              :label="u.username"
              :value="u.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="isBatchAssign">
          <span style="color: #909399">已选择 {{ selectedIds.length }} 条线索</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="assignDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="assignLoading" @click="handleAssignSubmit">确定</el-button>
      </template>
    </el-dialog>
    <!-- ── 转人工弹窗 ──────────────────────────────────────────────────────── -->
    <el-dialog v-model="transferDialogVisible" title="转为人工服务" width="420px" destroy-on-close>
      <el-form label-width="80px">
        <el-form-item label="销售人员">
          <el-select v-model="transferUserId" placeholder="选择销售人员" filterable style="width: 100%">
            <el-option
              v-for="u in salesUsers"
              :key="u.id"
              :label="u.username"
              :value="u.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="transferDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="transferLoading" @click="handleTransferSubmit">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Search, Connection, Switch, ChatDotRound } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import { getUsers } from '@/api/users'
import type { User } from '@/api/users'
import {
  getLeads, getLeadDetail, assignLead, batchAssignLeads,
  autoAssignLeads, updateLeadStatus, addFollowup,
  transferToHuman, markAsInvalid,
} from '@/api/leads'
import type { Lead, LeadDetail } from '@/api/leads'
import { getMessages } from '@/api/chat'
import type { ChatMessage } from '@/api/chat'

const router = useRouter()
const userStore = useUserStore()
const isAdmin = computed(() => userStore.role === 'admin')

// ── 筛选 & 列表 ────────────────────────────────────────────────────────────────
const filters = reactive({
  intent_level: '',
  status: '',
  search: '',
})
const dateRange = ref<[string, string] | null>(null)
const leadList = ref<Lead[]>([])
const tableLoading = ref(false)
const pagination = reactive({ page: 1, pageSize: 20, total: 0 })
const selectedIds = ref<number[]>([])

function formatDate(dateStr: string) {
  if (!dateStr) return ''
  return new Date(dateStr).toLocaleString('zh-CN')
}

function intentTagType(level: string) {
  const map: Record<string, string> = { high: 'danger', medium: 'warning', invalid: 'info' }
  return map[level] || 'info'
}

function intentLabel(level: string) {
  const map: Record<string, string> = { high: '高意向', medium: '中意向', invalid: '无效' }
  return map[level] || level
}

function statusTagType(status: string) {
  const map: Record<string, string> = {
    pending: 'info', assigned: '', following: 'warning', converted: 'success', closed: 'danger',
  }
  return map[status] || 'info'
}

function statusLabel(status: string) {
  const map: Record<string, string> = {
    pending: '待分配', assigned: '已分配', following: '跟进中', converted: '已转化', closed: '已关闭',
  }
  return map[status] || status
}

function chatStatusTagType(status: number) {
  const map: Record<number, string> = { 0: 'info', 1: 'success', 2: 'warning' }
  return map[status] ?? 'info'
}

function chatStatusLabel(status: number) {
  const map: Record<number, string> = { 0: '待处理', 1: '人工服务', 2: 'AI托管' }
  return map[status] ?? '-'
}

async function fetchLeads() {
  tableLoading.value = true
  try {
    const res: any = await getLeads({
      page: pagination.page,
      page_size: pagination.pageSize,
      intent_level: filters.intent_level || undefined,
      status: filters.status || undefined,
      start_date: dateRange.value?.[0] || undefined,
      end_date: dateRange.value?.[1] || undefined,
      search: filters.search || undefined,
    })
    if (res.code === 200) {
      leadList.value = res.data || []
      pagination.total = res.total
    }
  } finally {
    tableLoading.value = false
  }
}

function handleSearch() {
  pagination.page = 1
  fetchLeads()
}

function handleSelectionChange(rows: Lead[]) {
  selectedIds.value = rows.map(r => r.id)
}

// ── 线索详情 Drawer ────────────────────────────────────────────────────────────
const drawerVisible = ref(false)
const detailData = ref<LeadDetail | null>(null)
const detailAssignUser = ref<number | undefined>(undefined)
const recentMessages = ref<ChatMessage[]>([])

async function openDetail(row: Lead) {
  const res: any = await getLeadDetail(row.id)
  if (res.code === 200) {
    detailData.value = res.data
    detailAssignUser.value = res.data.assigned_to || undefined
    drawerVisible.value = true
    // 如果有对话状态，获取最近消息
    if (res.data.chat_status > 0) {
      fetchRecentMessages(res.data.id)
    } else {
      recentMessages.value = []
    }
  } else {
    ElMessage.error(res.message || '获取详情失败')
  }
}

async function fetchRecentMessages(leadId: number) {
  try {
    const res: any = await getMessages(leadId, 1, 10)
    if (res.code === 200) {
      recentMessages.value = res.data || []
    }
  } catch {}
}

// ── 状态流转 ────────────────────────────────────────────────────────────────────
const statusOptions = [
  { label: '待分配', value: 'pending' },
  { label: '已分配', value: 'assigned' },
  { label: '跟进中', value: 'following' },
  { label: '已转化', value: 'converted' },
  { label: '已关闭', value: 'closed' },
]

async function handleStatusChange(newStatus: string) {
  if (!detailData.value) return
  const res: any = await updateLeadStatus(detailData.value.id, newStatus)
  if (res.code === 200) {
    ElMessage.success('状态已更新')
    // 重新获取详情以刷新跟进记录
    await refreshDetail()
    fetchLeads()
  } else {
    ElMessage.error(res.message || '状态更新失败')
    // 恢复原状态
    const fresh: any = await getLeadDetail(detailData.value.id)
    if (fresh.code === 200) detailData.value.status = fresh.data.status
  }
}

async function refreshDetail() {
  if (!detailData.value) return
  const res: any = await getLeadDetail(detailData.value.id)
  if (res.code === 200) {
    detailData.value = res.data
    detailAssignUser.value = res.data.assigned_to || undefined
    // 刷新对话预览
    if (res.data.chat_status > 0) {
      fetchRecentMessages(res.data.id)
    } else {
      recentMessages.value = []
    }
  }
}

// ── 分配(详情内下拉) ──────────────────────────────────────────────────────────
async function handleDetailAssign(userId: number) {
  if (!detailData.value || !userId) return
  const res: any = await assignLead(detailData.value.id, userId)
  if (res.code === 200) {
    ElMessage.success('分配成功')
    await refreshDetail()
    fetchLeads()
  } else {
    ElMessage.error(res.message || '分配失败')
  }
}

// ── 分配弹窗 ────────────────────────────────────────────────────────────────────
const assignDialogVisible = ref(false)
const assignUserId = ref<number>()
const assignLoading = ref(false)
const isBatchAssign = ref(false)
const assignLeadId = ref<number | null>(null)

const assignDialogTitle = computed(() => isBatchAssign.value ? '批量分配线索' : '分配线索')

function openAssignDialog(row: Lead) {
  isBatchAssign.value = false
  assignLeadId.value = row.id
  assignUserId.value = row.assigned_to || undefined
  assignDialogVisible.value = true
}

function openBatchAssignDialog() {
  isBatchAssign.value = true
  assignLeadId.value = null
  assignUserId.value = undefined
  assignDialogVisible.value = true
}

async function handleAssignSubmit() {
  if (!assignUserId.value) {
    ElMessage.warning('请选择销售人员')
    return
  }
  assignLoading.value = true
  try {
    if (isBatchAssign.value) {
      const res: any = await batchAssignLeads(selectedIds.value, assignUserId.value)
      if (res.code === 200) {
        ElMessage.success(res.message || '批量分配成功')
        assignDialogVisible.value = false
        fetchLeads()
      } else {
        ElMessage.error(res.message || '分配失败')
      }
    } else if (assignLeadId.value) {
      const res: any = await assignLead(assignLeadId.value, assignUserId.value)
      if (res.code === 200) {
        ElMessage.success('分配成功')
        assignDialogVisible.value = false
        fetchLeads()
      } else {
        ElMessage.error(res.message || '分配失败')
      }
    }
  } finally {
    assignLoading.value = false
  }
}

// ── 自动分配 ────────────────────────────────────────────────────────────────────
const autoAssignLoading = ref(false)

async function handleAutoAssign() {
  autoAssignLoading.value = true
  try {
    const res: any = await autoAssignLeads()
    if (res.code === 200) {
      ElMessage.success(res.message || '自动分配完成')
      fetchLeads()
    } else {
      ElMessage.error(res.message || '自动分配失败')
    }
  } finally {
    autoAssignLoading.value = false
  }
}

// ── 跟进备注 ────────────────────────────────────────────────────────────────────
const followupContent = ref('')
const followupLoading = ref(false)

function followupTimelineType(action: string) {
  const map: Record<string, string> = { note: 'primary', status_change: 'warning', assign: 'success', chat: '' }
  return map[action] || 'info'
}

function followupActionLabel(action: string) {
  const map: Record<string, string> = { note: '备注', status_change: '状态变更', assign: '分配', chat: '聊天' }
  return map[action] || action
}

async function handleAddFollowup() {
  if (!detailData.value || !followupContent.value.trim()) return
  followupLoading.value = true
  try {
    const res: any = await addFollowup(detailData.value.id, { content: followupContent.value })
    if (res.code === 200) {
      ElMessage.success('备注已添加')
      followupContent.value = ''
      await refreshDetail()
    } else {
      ElMessage.error(res.message || '添加失败')
    }
  } finally {
    followupLoading.value = false
  }
}

// ── 进入聊天 ────────────────────────────────────────────────────────────────────
function goChat(row: Lead | LeadDetail) {
  router.push({ path: '/chat', query: { lead_id: String(row.id) } })
}

// ── 转人工弹窗 ──────────────────────────────────────────────────────────────────
const transferDialogVisible = ref(false)
const transferUserId = ref<number>()
const transferLoading = ref(false)
const transferLeadId = ref<number | null>(null)

function openTransferDialog(row: Lead | LeadDetail) {
  transferLeadId.value = row.id
  transferUserId.value = (row as Lead).assigned_to || undefined
  transferDialogVisible.value = true
}

async function handleTransferSubmit() {
  if (!transferUserId.value) {
    ElMessage.warning('请选择销售人员')
    return
  }
  if (!transferLeadId.value) return
  transferLoading.value = true
  try {
    const res: any = await transferToHuman(transferLeadId.value, transferUserId.value)
    if (res.code === 200) {
      ElMessage.success(res.message || '已转为人工服务')
      transferDialogVisible.value = false
      await refreshDetail()
      fetchLeads()
    } else {
      ElMessage.error(res.message || '转人工失败')
    }
  } finally {
    transferLoading.value = false
  }
}

// ── 标记无效 ────────────────────────────────────────────────────────────────────
async function handleMarkInvalid(row: Lead) {
  try {
    const res: any = await markAsInvalid(row.id)
    if (res.code === 200) {
      ElMessage.success(res.message || '已标记为无效')
      fetchLeads()
    } else {
      ElMessage.error(res.message || '标记失败')
    }
  } catch {
    // error handled by interceptor
  }
}

// ── 销售人员列表 ────────────────────────────────────────────────────────────────
const salesUsers = ref<User[]>([])

async function fetchSalesUsers() {
  const res: any = await getUsers({ page: 1, page_size: 200 })
  if (res.code === 200) {
    salesUsers.value = (res.data || []).filter((u: User) => u.status === 'active')
  }
}

// ── 初始化 ──────────────────────────────────────────────────────────────────────
onMounted(() => {
  fetchLeads()
  fetchSalesUsers()
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

.filter-card {
  .filter-row {
    display: flex;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
  }
  .filter-group {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .filter-label {
    color: #606266;
    font-size: 14px;
    white-space: nowrap;
  }
  .filter-actions {
    margin-left: auto;
    display: flex;
    gap: 8px;
  }
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

/* Drawer 详情 */
.detail-section {
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid #f0f0f0;

  &:last-child {
    border-bottom: none;
  }
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin: 0 0 12px 0;
}

.user-info-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user-meta {
  .user-nickname {
    font-size: 16px;
    font-weight: 500;
    color: #303133;
  }
  .user-uid {
    font-size: 13px;
    color: #909399;
    margin-top: 2px;
  }
}

.comment-box {
  background: #f5f7fa;
  padding: 12px;
  border-radius: 6px;
  font-size: 14px;
  color: #606266;
  line-height: 1.6;
}

.ai-info {
  .ai-reason {
    margin-top: 8px;
    color: #606266;
    font-size: 14px;
    line-height: 1.5;
  }
}

.source-info {
  font-size: 14px;
  color: #606266;
  line-height: 2;
}

.action-row {
  display: flex;
  align-items: center;
}

.chat-status-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.followup-item {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}

.followup-operator {
  font-weight: 500;
  color: #303133;
}

.followup-content {
  color: #606266;
}

/* AI对话预览 */
.chat-preview-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.chat-preview-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.5;

  &.outbound {
    background: #ecf5ff;
    .preview-direction {
      color: #409eff;
      font-weight: 600;
      flex-shrink: 0;
    }
    .preview-content {
      color: #303133;
    }
  }

  &.inbound {
    background: #f5f7fa;
    .preview-direction {
      color: #67c23a;
      font-weight: 600;
      flex-shrink: 0;
    }
    .preview-content {
      color: #606266;
    }
  }
}

.preview-content {
  word-break: break-word;
}
</style>
