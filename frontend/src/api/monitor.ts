import { get, post, put, del } from './index'
import service from './index'

export interface MonitorItem {
  id: number
  douyin_url: string
  douyin_uid: string
  nickname: string
  avatar: string
  status: string
  poll_interval_min: number
  created_by: number | null
  created_at: string
  source: string
  last_high_intent_at: string | null
  total_high_count: number
}

export function getMonitors(params?: any) {
  return get('/v1/monitors', params)
}

export function createMonitor(data: any) {
  return post('/v1/monitors', data)
}

export function batchImport(file: File) {
  const formData = new FormData()
  formData.append('file', file)
  return service.post('/v1/monitors/batch-import', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function updateMonitor(id: number, data: any) {
  return put(`/v1/monitors/${id}`, data)
}

export function deleteMonitor(id: number) {
  return del(`/v1/monitors/${id}`)
}

export function toggleMonitor(id: number) {
  return post(`/v1/monitors/${id}/toggle`)
}

export function runDiscovery() {
  return post('/v1/monitors/run-discovery')
}

export function runCleaning() {
  return post('/v1/monitors/run-cleaning')
}

export function getDiscoveryStats() {
  return get('/v1/monitors/discovery-stats')
}

export function getRemovedMonitors(params?: any) {
  return get('/v1/monitors/removed', params)
}

export function restoreMonitor(id: number) {
  return post(`/v1/monitors/${id}/restore`)
}
