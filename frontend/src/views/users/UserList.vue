<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">用户管理</h2>
    </div>
    <el-card>
      <template #header>
        <div class="flex-between">
          <div class="search-bar">
            <el-input
              v-model="searchText"
              placeholder="搜索用户名"
              clearable
              style="width: 240px"
              @clear="handleSearch"
              @keyup.enter="handleSearch"
            >
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
            <el-button type="primary" @click="handleSearch">搜索</el-button>
          </div>
          <el-button type="primary" @click="openCreateDialog">
            <el-icon style="margin-right: 4px"><Plus /></el-icon>新增用户
          </el-button>
        </div>
      </template>

      <el-table :data="userList" stripe v-loading="tableLoading" style="width: 100%">
        <el-table-column prop="username" label="用户名" min-width="120" />
        <el-table-column prop="role" label="角色" width="120">
          <template #default="{ row }">
            <el-tag :type="row.role === 'admin' ? 'danger' : 'info'">
              {{ row.role === 'admin' ? '管理员' : '销售' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'warning'">
              {{ row.status === 'active' ? '正常' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link @click="openEditDialog(row)">编辑</el-button>
            <el-button type="warning" link @click="openResetPwdDialog(row)">重置密码</el-button>
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
          @size-change="fetchUsers"
          @current-change="fetchUsers"
        />
      </div>
    </el-card>

    <!-- Create User Dialog -->
    <el-dialog v-model="createDialogVisible" title="新增用户" width="460px" destroy-on-close>
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-width="80px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="createForm.username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="createForm.password" type="password" placeholder="请输入密码" show-password />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="createForm.role" placeholder="请选择角色" style="width: 100%">
            <el-option label="管理员" value="admin" />
            <el-option label="销售" value="sales" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleCreate">确定</el-button>
      </template>
    </el-dialog>

    <!-- Edit User Dialog -->
    <el-dialog v-model="editDialogVisible" title="编辑用户" width="460px" destroy-on-close>
      <el-form ref="editFormRef" :model="editForm" label-width="80px">
        <el-form-item label="用户名">
          <el-input :model-value="editForm.username" disabled />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="editForm.role" placeholder="请选择角色" style="width: 100%">
            <el-option label="管理员" value="admin" />
            <el-option label="销售" value="sales" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态" prop="status">
          <el-select v-model="editForm.status" placeholder="请选择状态" style="width: 100%">
            <el-option label="正常" value="active" />
            <el-option label="禁用" value="disabled" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleEdit">确定</el-button>
      </template>
    </el-dialog>

    <!-- Reset Password Dialog -->
    <el-dialog v-model="resetPwdDialogVisible" title="重置密码" width="460px" destroy-on-close>
      <el-form ref="resetPwdFormRef" :model="resetPwdForm" :rules="resetPwdRules" label-width="80px">
        <el-form-item label="用户名">
          <el-input :model-value="resetPwdForm.username" disabled />
        </el-form-item>
        <el-form-item label="新密码" prop="newPassword">
          <el-input v-model="resetPwdForm.newPassword" type="password" placeholder="请输入新密码" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetPwdDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleResetPwd">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Plus } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import { getUsers, createUser, updateUser, deleteUser, resetPassword } from '@/api/users'
import type { User } from '@/api/users'

// ── Table state ──
const userList = ref<User[]>([])
const tableLoading = ref(false)
const searchText = ref('')
const pagination = reactive({ page: 1, pageSize: 20, total: 0 })

function formatDate(dateStr: string) {
  if (!dateStr) return ''
  return new Date(dateStr).toLocaleString('zh-CN')
}

async function fetchUsers() {
  tableLoading.value = true
  try {
    const res = await getUsers({
      page: pagination.page,
      page_size: pagination.pageSize,
      search: searchText.value || undefined,
    })
    if (res.code === 200) {
      userList.value = res.data
      pagination.total = res.total
    }
  } finally {
    tableLoading.value = false
  }
}

function handleSearch() {
  pagination.page = 1
  fetchUsers()
}

// ── Create dialog ──
const createDialogVisible = ref(false)
const createFormRef = ref<FormInstance>()
const submitLoading = ref(false)

const createForm = reactive({ username: '', password: '', role: 'sales' })
const createRules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码长度不能少于6位', trigger: 'blur' },
  ],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }],
}

function openCreateDialog() {
  createForm.username = ''
  createForm.password = ''
  createForm.role = 'sales'
  createDialogVisible.value = true
}

async function handleCreate() {
  if (!createFormRef.value) return
  const valid = await createFormRef.value.validate().catch(() => false)
  if (!valid) return
  submitLoading.value = true
  try {
    const res = await createUser(createForm)
    if (res.code === 200) {
      ElMessage.success('用户创建成功')
      createDialogVisible.value = false
      fetchUsers()
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
const editForm = reactive({ id: 0, username: '', role: '', status: '' })

function openEditDialog(row: User) {
  editForm.id = row.id
  editForm.username = row.username
  editForm.role = row.role
  editForm.status = row.status
  editDialogVisible.value = true
}

async function handleEdit() {
  submitLoading.value = true
  try {
    const res = await updateUser(editForm.id, { role: editForm.role, status: editForm.status })
    if (res.code === 200) {
      ElMessage.success('更新成功')
      editDialogVisible.value = false
      fetchUsers()
    } else {
      ElMessage.error(res.message || '更新失败')
    }
  } finally {
    submitLoading.value = false
  }
}

// ── Reset password dialog ──
const resetPwdDialogVisible = ref(false)
const resetPwdFormRef = ref<FormInstance>()
const resetPwdForm = reactive({ id: 0, username: '', newPassword: '' })
const resetPwdRules: FormRules = {
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '密码长度不能少于6位', trigger: 'blur' },
  ],
}

function openResetPwdDialog(row: User) {
  resetPwdForm.id = row.id
  resetPwdForm.username = row.username
  resetPwdForm.newPassword = ''
  resetPwdDialogVisible.value = true
}

async function handleResetPwd() {
  if (!resetPwdFormRef.value) return
  const valid = await resetPwdFormRef.value.validate().catch(() => false)
  if (!valid) return
  submitLoading.value = true
  try {
    const res = await resetPassword(resetPwdForm.id, resetPwdForm.newPassword)
    if (res.code === 200) {
      ElMessage.success('密码重置成功')
      resetPwdDialogVisible.value = false
    } else {
      ElMessage.error(res.message || '重置失败')
    }
  } finally {
    submitLoading.value = false
  }
}

// ── Delete ──
async function handleDelete(row: User) {
  try {
    await ElMessageBox.confirm(`确定要删除用户「${row.username}」吗？`, '删除确认', {
      type: 'warning',
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  submitLoading.value = true
  try {
    const res = await deleteUser(row.id)
    if (res.code === 200) {
      ElMessage.success('删除成功')
      fetchUsers()
    } else {
      ElMessage.error(res.message || '删除失败')
    }
  } finally {
    submitLoading.value = false
  }
}

// ── Init ──
onMounted(() => {
  fetchUsers()
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

.search-bar {
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
