import { get, post } from './index'

export function getDmQueueStats() {
  return get('/v1/dm-queue/stats')
}

export function getDmQueueList(params?: {
  page?: number
  page_size?: number
  status?: string
}) {
  return get('/v1/dm-queue/list', params)
}

export function pauseDmQueue() {
  return post('/v1/dm-queue/pause')
}

export function resumeDmQueue() {
  return post('/v1/dm-queue/resume')
}
