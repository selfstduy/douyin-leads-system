import { get, post, del } from './index'

// ── 风控统计 & 状态 ──────────────────────────────────────────

export function getRiskStats() {
  return get('/risk/stats')
}

export function getRiskStatus() {
  return get('/risk/status')
}

export function resumeSending() {
  return post('/risk/resume')
}

// ── 黑名单管理 ──────────────────────────────────────────────

export function getBlacklist(params?: {
  page?: number
  page_size?: number
}) {
  return get('/risk/blacklist', params)
}

export function addBlacklist(data: {
  user_uid: string
  reason?: string
}) {
  return post('/risk/blacklist', data)
}

export function removeBlacklist(userUid: string) {
  return del(`/risk/blacklist/${userUid}`)
}

// ── 事件记录(webhook) ───────────────────────────────────────

export function reportEvent(data: {
  event_type: string
  user_uid?: string
  count?: number
}) {
  return post('/risk/report-event', data)
}
