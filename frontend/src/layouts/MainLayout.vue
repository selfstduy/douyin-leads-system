<template>
  <el-container class="main-layout">
    <!-- Sidebar -->
    <el-aside :width="appStore.sidebarCollapsed ? '64px' : '220px'" class="sidebar">
      <div class="logo">
        <h2 v-if="!appStore.sidebarCollapsed">CRM系统</h2>
        <h2 v-else>CRM</h2>
      </div>
      <el-menu
        :default-active="route.path"
        :collapse="appStore.sidebarCollapsed"
        :router="true"
        background-color="#304156"
        text-color="#bfcbd9"
        active-text-color="#409eff"
        class="sidebar-menu"
      >
        <template v-for="item in menuItems" :key="item.path">
          <el-menu-item :index="item.path">
            <el-icon><component :is="item.icon" /></el-icon>
            <template #title>{{ item.title }}</template>
          </el-menu-item>
        </template>
      </el-menu>
    </el-aside>

    <!-- Main content -->
    <el-container>
      <!-- Header -->
      <el-header class="header">
        <div class="header-left">
          <el-icon class="collapse-btn" @click="appStore.toggleSidebar">
            <component :is="appStore.sidebarCollapsed ? 'Expand' : 'Fold'" />
          </el-icon>
        </div>
        <div class="header-right">
          <!-- 告警通知 -->
          <el-badge :value="unreadAlertCount" :hidden="unreadAlertCount === 0" :max="99" class="alert-badge">
            <el-icon class="alert-icon" @click="goToAlerts">
              <Bell />
            </el-icon>
          </el-badge>
          <el-dropdown @command="handleCommand">
            <span class="user-info">
              <el-avatar :size="32" :icon="UserFilled" />
              <span class="username">{{ userStore.username }}</span>
              <el-icon><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">个人信息</el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <!-- Main content area -->
      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useAppStore } from '@/stores/app'
import { UserFilled, ArrowDown, Bell } from '@element-plus/icons-vue'
import { getUnreadAlertCount } from '@/api/system'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const appStore = useAppStore()
const unreadAlertCount = ref(0)

const allMenuItems = [
  { path: '/dashboard', title: '仪表盘', icon: 'Odometer', roles: [] },
  { path: '/monitor', title: '监控管理', icon: 'Monitor', roles: [] },
  { path: '/leads', title: '线索管理', icon: 'User', roles: [] },
  { path: '/chat', title: '聊天', icon: 'ChatDotRound', roles: [] },
  { path: '/users', title: '用户管理', icon: 'UserFilled', roles: ['admin'] },
  { path: '/douyin-accounts', title: '抖音账号', icon: 'ChatLineRound', roles: ['admin'] },
  { path: '/alerts', title: '告警中心', icon: 'Bell', roles: [] },
  { path: '/system-config', title: '参数配置', icon: 'Setting', roles: ['admin'] },
]

const menuItems = computed(() => {
  return allMenuItems.filter((item) => {
    if (!item.roles || item.roles.length === 0) return true
    return item.roles.includes(userStore.role)
  })
})

function handleCommand(command: string) {
  if (command === 'logout') {
    userStore.logout()
  }
}

function goToAlerts() {
  router.push('/alerts')
}

async function fetchUnreadAlerts() {
  try {
    const res = await getUnreadAlertCount()
    if (res.code === 200) {
      unreadAlertCount.value = res.data.unread_count || 0
    }
  } catch (e) {
    // 静默失败
  }
}

onMounted(() => {
  fetchUnreadAlerts()
})
</script>

<style scoped lang="scss">
.main-layout {
  height: 100vh;
}

.sidebar {
  background-color: #304156;
  transition: width 0.3s;
  overflow: hidden;

  .logo {
    height: 60px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #fff;
    background-color: #263445;

    h2 {
      font-size: 18px;
      white-space: nowrap;
    }
  }

  .sidebar-menu {
    border-right: none;
    height: calc(100vh - 60px);
    overflow-y: auto;
  }
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  box-shadow: 0 1px 4px rgba(0, 21, 41, 0.08);
  padding: 0 20px;

  .header-left {
    display: flex;
    align-items: center;
  }

  .collapse-btn {
    font-size: 20px;
    cursor: pointer;
    color: #666;

    &:hover {
      color: #409eff;
    }
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 20px;
  }

  .alert-badge {
    cursor: pointer;
  }

  .alert-icon {
    font-size: 20px;
    color: #666;
    cursor: pointer;

    &:hover {
      color: #409eff;
    }
  }

  .user-info {
    display: flex;
    align-items: center;
    cursor: pointer;
    gap: 8px;

    .username {
      color: #333;
      font-size: 14px;
    }
  }
}

.main-content {
  background-color: #f5f7fa;
  overflow-y: auto;
}
</style>
