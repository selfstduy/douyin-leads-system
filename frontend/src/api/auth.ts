import { post, get } from './index'

export interface LoginParams {
  username: string
  password: string
}

export interface UserInfo {
  id: number
  username: string
  role: string
  status: string
  created_at: string
}

export interface LoginResponseData {
  token: string
  user: UserInfo
}

export interface ApiResponse<T = any> {
  code: number
  message: string
  data: T
}

export function login(data: LoginParams) {
  return post<ApiResponse<LoginResponseData>>('/v1/auth/login', data)
}

export function register(data: { username: string; password: string; role?: string }) {
  return post<ApiResponse>('/v1/auth/register', data)
}

export function getMe() {
  return get<ApiResponse<UserInfo>>('/v1/auth/me')
}

export function refreshToken() {
  return post<ApiResponse>('/v1/auth/refresh')
}

export function logout() {
  return post('/v1/auth/logout')
}
