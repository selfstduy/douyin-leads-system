import { useUserStore } from '@/stores/user'

export function hasRole(role: string): boolean {
  const userStore = useUserStore()
  return userStore.role === role
}

export function hasAnyRole(roles: string[]): boolean {
  const userStore = useUserStore()
  return roles.includes(userStore.role)
}

export function isAdmin(): boolean {
  return hasRole('admin')
}
