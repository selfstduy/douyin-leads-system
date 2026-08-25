<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">抖音账号管理</h2>
    </div>
    <el-card>
      <template #header>
        <div class="flex-between">
          <span class="header-tip">每个销售最多可绑定 10 个账号</span>
          <el-button type="primary" @click="openAddDialog">
            <el-icon style="margin-right: 4px"><Plus /></el-icon>添加账号
          </el-button>
        </div>
      </template>

      <el-table :data="accounts" stripe v-loading="tableLoading" style="width: 100%">
        <el-table-column prop="nickname" label="昵称" min-width="120" />
        <el-table-column prop="douyin_uid" label="抖音UID" min-width="140" />
        <el-table-column label="分配给" min-width="100">
          <template #default="{ row }">
            <span v-if="row.assigned_to_username">{{ row.assigned_to_username }}</span>
            <el-tag v-else type="info" size="small">未分配</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="登录状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.login_status)" size="small">
              {{ statusLabel(row.login_status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最后活跃" width="170">
          <template #default="{ row }">
            {{ formatDate(row.last_active_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="300" fixed="right">
          <template #default="{ row }">
            <el-button v-if="!row.assigned_to_user_id" type="primary" link @click="openAssignDialog(row)">分配</el-button>
            <el-button v-else type="warning" link @click="handleUnassign(row)">取消分配</el-button>
            <el-button type="info" link @click="openCookieDialog(row)">更新Cookie</el-button>
            <el-button type="success" link @click="handleCheckStatus(row)">检查状态</el-button>
            <el-button type="danger" link @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Add Account Dialog -->
    <el-dialog v-model="addDialogVisible" title="添加抖音账号" width="500px" destroy-on-close>
      <el-form ref="addFormRef" :model="addForm" :rules="addRules" label-width="90px">
        <el-form-item label="抖音UID" prop="douyin_uid">
          <el-input v-model="addForm.douyin_uid" placeholder="请输入抖音UID" />
        </el-form-item>
        <el-form-item label="昵称" prop="nickname">
          <el-input v-model="addForm.nickname" placeholder="请输入账号昵称" />
        </el-form-item>
        <el-form-item label="Cookie" prop="cookie_data">
          <el-input v-model="addForm.cookie_data" type="textarea" :rows="4" placeholder="请粘贴Cookie数据" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleAdd">确定</el-button>
      </template>
    </el-dialog>

    <!-- Assign Dialog -->
    <el-dialog v-model="assignDialogVisible" title="分配账号" width="400px" destroy-on-close>
      <el-form label-width="80px">
        <el-form-item label="分配给">
          <el-select v-model="assignUserId" placeholder="选择用户" style="width: 100%" filterable>
            <el-option v-for="u in userList" :key="u.id" :label="u.username" :value="u.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="assignDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleAssign">确定</el-button>
      </template>
    </el-dialog>

    <!-- Cookie Dialog -->
    <el-dialog v-model="cookieDialogVisible" title="更新Cookie" width="500px" destroy-on-close>
      <el-form label-width="80px">
        <el-form-item label="Cookie">
          <el-input v-model="cookieData" type="textarea" :rows="6" placeholder="请粘贴新的Cookie数据" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="cookieDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleUpdateCookie">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import {
  getAccounts, addAccount, assignAccount, unassignAccount,
  updateCookie, checkAccountStatus, deleteAccount
} from '@/api/douyinAccounts'
import type { DouyinAccountInfo } from '@/api/douyinAccounts'
import { getUsers } from '@/api/users'
import type { User } from '@/api/users'

// ── Table ──
const accounts = ref<DouyinAccountInfo[]>([])
const tableLoading = ref(false)

function statusType(status: string) {
  if (status === 'online') return 'success'
  if (status === 'expired') return 'danger'
  return 'info'
}

function statusLabel(status: string) {
  if (status === 'online') return '在线'
  if (status === 'expired') return '失效'
  return '离线'
}

function formatDate(dateStr: string | null) {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

async function fetchAccounts() {
  tableLoading.value = true
  try {
    const res = await getAccounts()
    if (res.code === 200) {
      accounts.value = res.data || []
    }
  } finally {
    tableLoading.value = false
  }
}

// ── Add ──
const addDialogVisible = ref(false)
const addFormRef = ref<FormInstance>()
const submitLoading = ref(false)
const addForm = reactive({ douyin_uid: '', nickname: '', cookie_data: '' })
const addRules: FormRules = {
  douyin_uid: [{ required: true, message: '请输入抖音UID', trigger: 'blur' }],
  nickname: [{ required: true, message: '请输入昵称', trigger: 'blur' }],
  cookie_data: [{ required: true, message: '请输入Cookie', trigger: 'blur' }],
}

function openAddDialog() {
  addForm.douyin_uid = ''
  addForm.nickname = ''
  addForm.cookie_data = ''
  addDialogVisible.value = true
}

async function handleAdd() {
  if (!addFormRef.value) return
  const valid = await addFormRef.value.validate().catch(() => false)
  if (!valid) return
  submitLoading.value = true
  try {
    const res = await addAccount(addForm)
    if (res.code === 200) {
      ElMessage.success('账号添加成功')
      addDialogVisible.value = false
      fetchAccounts()
    } else {
      ElMessage.error(res.message || '添加失败')
    }
  } finally {
    submitLoading.value = false
  }
}

// ── Assign ──
const assignDialogVisible = ref(false)
const assignUserId = ref<number | null>(null)
const currentAssignAccount = ref<DouyinAccountInfo | null>(null)
const userList = ref<User[]>([])

async function openAssignDialog(row: DouyinAccountInfo) {
  currentAssignAccount.value = row
  assignUserId.value = null
  assignDialogVisible.value = true
  // Load user list
  try {
    const res = await getUsers({ page: 1, page_size: 100 })
    if (res.code === 200) {
      userList.value = (res.data || []).filter(u => u.role === 'sales' && u.status === 'active')
    }
  } catch {}
}

async function handleAssign() {
  if (!assignUserId.value || !currentAssignAccount.value) return
  submitLoading.value = true
  try {
    const res = await assignAccount(currentAssignAccount.value.id, assignUserId.value)
    if (res.code === 200) {
      ElMessage.success('分配成功')
      assignDialogVisible.value = false
      fetchAccounts()
    } else {
      ElMessage.error(res.message || '分配失败')
    }
  } finally {
    submitLoading.value = false
  }
}

async function handleUnassign(row: DouyinAccountInfo) {
  try {
    await ElMessageBox.confirm(`确定要取消分配账号「${row.nickname}」吗？`, '确认', { type: 'warning' })
  } catch { return }
  submitLoading.value = true
  try {
    const res = await unassignAccount(row.id)
    if (res.code === 200) {
      ElMessage.success('已取消分配')
      fetchAccounts()
    }
  } finally {
    submitLoading.value = false
  }
}

// ── Cookie ──
const cookieDialogVisible = ref(false)
const cookieAccountId = ref<number | null>(null)
const cookieData = ref('')

function openCookieDialog(row: DouyinAccountInfo) {
  cookieAccountId.value = row.id
  cookieData.value = ''
  cookieDialogVisible.value = true
}

async function handleUpdateCookie() {
  if (!cookieAccountId.value || !cookieData.value.trim()) return
  submitLoading.value = true
  try {
    const res = await updateCookie(cookieAccountId.value, cookieData.value)
    if (res.code === 200) {
      ElMessage.success('Cookie已更新')
      cookieDialogVisible.value = false
      fetchAccounts()
    }
  } finally {
    submitLoading.value = false
  }
}

// ── Status check ──
async function handleCheckStatus(row: DouyinAccountInfo) {
  try {
    const res = await checkAccountStatus(row.id)
    if (res.code === 200 && res.data) {
      const s = res.data.status
      ElMessage.success(`账号状态: ${s === 'online' ? '在线' : s === 'expired' ? '失效' : '离线'}`)
      fetchAccounts()
    }
  } catch {}
}

// ── Delete ──
async function handleDelete(row: DouyinAccountInfo) {
  try {
    await ElMessageBox.confirm(`确定要删除账号「${row.nickname}」吗？`, '删除确认', {
      type: 'warning', confirmButtonText: '确定', cancelButtonText: '取消'
    })
  } catch { return }
  submitLoading.value = true
  try {
    const res = await deleteAccount(row.id)
    if (res.code === 200) {
      ElMessage.success('删除成功')
      fetchAccounts()
    }
  } finally {
    submitLoading.value = false
  }
}

// ── Init ──
onMounted(() => {
  fetchAccounts()
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

.header-tip {
  font-size: 13px;
  color: #909399;
}
</style>
