import { get, post } from './index'
import type { ApiResponse } from './auth'

export interface ChatSession {
  lead_id: number
  lead_nickname: string
  lead_uid: string
  last_message: string | null
  last_message_at: string | null
  unread_count: number
  intent_level: string
  chat_status: number  // 0=待处理, 1=人工服务, 2=AI托管
  chat_id: string | null
}

export interface ChatMessage {
  id: number
  lead_id: number
  douyin_account_id: number
  direction: string
  content: string
  msg_type: string
  sent_at: string
  status: string
  is_ai?: boolean  // 标记是否为AI回复
  chat_status?: number  // WebSocket推送时携带的对话状态
  chat_id?: string
}

export interface DouyinAccount {
  id: number
  douyin_uid: string
  nickname: string
  login_status: string
}

export function getSessions() {
  return get<ApiResponse<ChatSession[]>>('/v1/chat/sessions')
}

export function getMessages(leadId: number, page: number = 1, pageSize: number = 50) {
  return get<any>(`/v1/chat/messages/${leadId}`, { page, page_size: pageSize })
}

export function sendMessage(data: { lead_id: number; content: string; douyin_account_id?: number }) {
  return post<ApiResponse>('/v1/chat/send', data)
}

export function getAvailableAccounts() {
  return get<ApiResponse<DouyinAccount[]>>('/v1/chat/accounts')
}
