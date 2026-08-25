import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login as loginApi, getMe, logout as logoutApi } from '@/api/auth'
import type { UserInfo, LoginParams } from '@/api/auth'
import router from '@/router'

export const useUserStore = defineStore('user', () => {
  const token = ref<string>(localStorage.getItem('token') || '')
  const userInfo = ref<UserInfo | null>(
    localStorage.getItem('userInfo') ? JSON.parse(localStorage.getItem('userInfo')!) : null
  )

  const isLoggedIn = computed(() => !!token.value)
  const role = computed(() => userInfo.value?.role || '')
  const username = computed(() => userInfo.value?.username || '')

  async function login(params: LoginParams) {
    const res = await loginApi(params)
    if (res.code !== 200) {
      throw new Error(res.message || '登录失败')
    }
    token.value = res.data.token
    userInfo.value = res.data.user
    localStorage.setItem('token', res.data.token)
    localStorage.setItem('userInfo', JSON.stringify(res.data.user))
    return res.data
  }

  async function fetchUserInfo() {
    const res = await getMe()
    if (res.code === 200 && res.data) {
      userInfo.value = res.data
      localStorage.setItem('userInfo', JSON.stringify(res.data))
    }
    return res.data
  }

  function logout() {
    logoutApi().catch(() => {})
    token.value = ''
    userInfo.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('userInfo')
    router.push('/login')
  }

  return {
    token,
    userInfo,
    isLoggedIn,
    role,
    username,
    login,
    fetchUserInfo,
    logout,
  }
})
