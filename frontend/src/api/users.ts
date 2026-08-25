import { get, post, put, del } from './index'
import type { ApiResponse } from './auth'

export interface User {
  id: number
  username: string
  role: string
  status: string
  created_at: string
}

export interface UserListParams {
  page?: number
  page_size?: number
  search?: string
}

export interface PageData<T> {
  code: number
  message: string
  data: T[]
  total: number
  page: number
  page_size: number
}

export function getUsers(params?: UserListParams) {
  return get<PageData<User>>('/v1/users', params)
}

export function getUserDetail(id: number) {
  return get<ApiResponse<User>>(`/v1/users/${id}`)
}

export function createUser(data: { username: string; password: string; role?: string }) {
  return post<ApiResponse>('/v1/auth/register', data)
}

export function updateUser(id: number, data: { role?: string; status?: string }) {
  return put<ApiResponse>(`/v1/users/${id}`, data)
}

export function deleteUser(id: number) {
  return del<ApiResponse>(`/v1/users/${id}`)
}

export function resetPassword(id: number, new_password: string) {
  return post<ApiResponse>(`/v1/users/${id}/reset-password`, { new_password })
}
