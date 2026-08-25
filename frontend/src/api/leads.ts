import { get, post, put } from './index'
import type { ApiResponse } from './auth'
import type { PageData } from './users'

// ── Types ──────────────────────────────────────────────────────────────────────

export interface Lead {
  id: number
  comment_id: number
  video_id: number
  user_uid: string
  user_nickname: string
  user_avatar: string
  intent_level: string  // high / medium / invalid
  ai_reason: string
  status: string  // pending / assigned / following / converted / closed
  chat_status: number  // 0=待处理, 1=人工服务, 2=AI托管
  assigned_to: number | null
  assigned_to_name: string | null
  assigned_at: string | null
  created_at: string
  comment_content: string
  video_title: string
}

export interface LeadDetail extends Lead {
  monitor_account_name: string
  followups: Followup[]
}

export interface Followup {
  id: number
  lead_id: number
  operator_id: number
  operator_name: string
  action: string  // note / status_change / assign / chat
  content: string
  created_at: string
}

export interface LeadListParams {
  page?: number
  page_size?: number
  intent_level?: string
  status?: string
  assigned_to?: number
  start_date?: string
  end_date?: string
  search?: string
}

// ── API ────────────────────────────────────────────────────────────────────────

export function getLeads(params?: LeadListParams) {
  return get<PageData<Lead>>('/v1/leads', params)
}

export function getLeadDetail(id: number) {
  return get<ApiResponse<LeadDetail>>(`/v1/leads/${id}`)
}

export function assignLead(id: number, userId: number) {
  return post<ApiResponse>(`/v1/leads/${id}/assign`, { user_id: userId })
}

export function batchAssignLeads(leadIds: number[], userId: number) {
  return post<ApiResponse>('/v1/leads/batch-assign', { lead_ids: leadIds, user_id: userId })
}

export function autoAssignLeads() {
  return post<ApiResponse>('/v1/leads/auto-assign')
}

export function updateLeadStatus(id: number, status: string) {
  return put<ApiResponse>(`/v1/leads/${id}/status`, { status })
}

export function addFollowup(id: number, data: { action?: string; content: string }) {
  return post<ApiResponse>(`/v1/leads/${id}/followup`, { action: data.action || 'note', content: data.content })
}

export function getFollowups(id: number) {
  return get<ApiResponse<Followup[]>>(`/v1/leads/${id}/followups`)
}

export function transferToHuman(id: number, salesUserId: number) {
  return post<ApiResponse>(`/v1/leads/${id}/transfer-to-human`, { sales_user_id: salesUserId })
}

export function markAsInvalid(id: number) {
  return post<ApiResponse>(`/v1/leads/${id}/mark-invalid`)
}
