import { get, post, put, del } from './index'
import type { ApiResponse } from './auth'

export interface DouyinAccountInfo {
  id: number
  douyin_uid: string
  nickname: string
  login_status: string
  assigned_to_user_id: number | null
  assigned_to_username: string | null
  last_active_at: string | null
  created_at: string | null
}

export function getAccounts() {
  return get<ApiResponse<DouyinAccountInfo[]>>('/v1/douyin-accounts')
}

export function addAccount(data: { douyin_uid: string; nickname: string; cookie_data: string }) {
  return post<ApiResponse>('/v1/douyin-accounts', data)
}

export function assignAccount(id: number, userId: number) {
  return put<ApiResponse>(`/v1/douyin-accounts/${id}/assign`, { user_id: userId })
}

export function unassignAccount(id: number) {
  return put<ApiResponse>(`/v1/douyin-accounts/${id}/unassign`)
}

export function updateCookie(id: number, cookieData: string) {
  return put<ApiResponse>(`/v1/douyin-accounts/${id}/cookie`, { cookie_data: cookieData })
}

export function checkAccountStatus(id: number) {
  return get<ApiResponse>(`/v1/douyin-accounts/${id}/status`)
}

export function deleteAccount(id: number) {
  return del<ApiResponse>(`/v1/douyin-accounts/${id}`)
}
