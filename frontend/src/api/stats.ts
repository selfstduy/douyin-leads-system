import { get } from './index'
import axios from 'axios'

export function getDashboard() {
  return get('/stats/dashboard')
}

export function getSalesPerformance(params?: { start_date?: string; end_date?: string }) {
  return get('/stats/sales-performance', params)
}

export function getMonitorStats(params?: { start_date?: string; end_date?: string }) {
  return get('/stats/monitor-stats', params)
}

export function getTrend(days = 7) {
  return get('/stats/trend', { days })
}

export function exportLeads(params?: {
  status?: string
  intent_level?: string
  assigned_to?: number
  start_date?: string
  end_date?: string
}) {
  const token = localStorage.getItem('token')
  const query = new URLSearchParams()
  if (params?.status) query.set('status', params.status)
  if (params?.intent_level) query.set('intent_level', params.intent_level)
  if (params?.assigned_to) query.set('assigned_to', String(params.assigned_to))
  if (params?.start_date) query.set('start_date', params.start_date)
  if (params?.end_date) query.set('end_date', params.end_date)
  const qs = query.toString()
  const url = `/api/stats/export${qs ? '?' + qs : ''}`
  return axios.get(url, {
    responseType: 'blob',
    headers: { Authorization: `Bearer ${token}` },
  })
}
