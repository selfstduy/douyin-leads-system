import { get, post, put, del } from './index'

export interface TopicMonitorItem {
  id: number
  topic: string
  description: string
  industry: string
  status: string
  poll_interval_min: number
  created_by: number | null
  created_at: string
}

export function getTopicMonitors(params?: any) {
  return get('/v1/topic-monitors', params)
}

export function createTopicMonitor(data: any) {
  return post('/v1/topic-monitors', data)
}

export function updateTopicMonitor(id: number, data: any) {
  return put(`/v1/topic-monitors/${id}`, data)
}

export function deleteTopicMonitor(id: number) {
  return del(`/v1/topic-monitors/${id}`)
}

export function toggleTopicMonitor(id: number) {
  return post(`/v1/topic-monitors/${id}/toggle`)
}
