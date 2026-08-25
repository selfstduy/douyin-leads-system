<template>
  <div class="chat-container">
    <!-- Left: Session list -->
    <div class="session-panel">
      <div class="session-header">
        <el-input
          v-model="searchText"
          placeholder="搜索线索..."
          clearable
          size="default"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
      </div>
      <div class="session-list">
        <div
          v-for="session in filteredSessions"
          :key="session.lead_id"
          :class="['session-item', { active: currentLeadId === session.lead_id }]"
          @click="selectSession(session)"
        >
          <div class="session-info">
            <div class="session-top">
              <span class="session-name">{{ session.lead_nickname || session.lead_uid }}</span>
              <span class="session-time">{{ formatTime(session.last_message_at) }}</span>
            </div>
            <div class="session-bottom">
              <span class="session-preview">{{ session.last_message || '暂无消息' }}</span>
              <el-badge v-if="session.unread_count > 0" :value="session.unread_count" :max="99" class="unread-badge" />
            </div>
          </div>
          <div class="session-tags">
            <el-tag v-if="session.chat_status === 2" type="warning" size="small" class="chat-status-tag" effect="dark">
              <el-icon style="margin-right: 2px"><MagicStick /></el-icon>AI
            </el-tag>
            <el-tag v-else-if="session.chat_status === 1" type="success" size="small" class="chat-status-tag">人工</el-tag>
            <el-tag v-if="session.intent_level === 'high'" type="danger" size="small" class="intent-tag">高意向</el-tag>
            <el-tag v-else-if="session.intent_level === 'medium'" type="warning" size="small" class="intent-tag">中意向</el-tag>
          </div>
        </div>
        <div v-if="sessionsLoading" class="session-loading">
          <el-icon class="is-loading"><Loading /></el-icon>
        </div>
        <div v-if="!sessionsLoading && sessions.length === 0" class="session-empty">
          <el-empty description="暂无线索对话" :image-size="60" />
        </div>
      </div>
    </div>

    <!-- Right: Chat area -->
    <div class="chat-panel">
      <template v-if="currentSession">
        <!-- Header -->
        <div class="chat-header">
          <div class="chat-header-info">
            <span class="chat-header-name">{{ currentSession.lead_nickname || currentSession.lead_uid }}</span>
            <span class="chat-header-uid">UID: {{ currentSession.lead_uid }}</span>
            <el-tag
              v-if="currentSession.chat_status === 2"
              type="warning"
              size="small"
              effect="dark"
              class="chat-header-status"
            >
              <el-icon style="margin-right: 2px"><MagicStick /></el-icon>AI自动跟进
            </el-tag>
            <el-tag
              v-else-if="currentSession.chat_status === 1"
              type="success"
              size="small"
              class="chat-header-status"
            >人工服务</el-tag>
          </div>
          <div class="chat-header-actions">
            <el-select v-model="selectedAccountId" placeholder="选择发送账号" size="small" style="width: 180px">
              <el-option
                v-for="acc in availableAccounts"
                :key="acc.id"
                :label="acc.nickname"
                :value="acc.id"
              />
            </el-select>
          </div>
        </div>

        <!-- Messages -->
        <div class="message-area" ref="messageAreaRef">
          <div v-if="messagesLoading" class="messages-loading">
            <el-icon class="is-loading"><Loading /></el-icon> 加载中...
          </div>
          <div v-for="msg in messages" :key="msg.id" :class="['message-row', msg.direction]">
            <div class="message-bubble">
              <div v-if="msg.direction === 'outbound' && msg.is_ai" class="message-ai-label">
                <el-icon><MagicStick /></el-icon> AI回复
              </div>
              <div class="message-content">{{ msg.content }}</div>
              <div class="message-meta">
                <span class="message-time">{{ formatMessageTime(msg.sent_at) }}</span>
                <span v-if="msg.direction === 'outbound'" class="message-status">
                  <el-icon v-if="msg.status === 'sent'" color="#67c23a"><Check /></el-icon>
                  <el-icon v-else-if="msg.status === 'failed'" color="#f56c6c"><WarningFilled /></el-icon>
                </span>
              </div>
            </div>
          </div>
          <div v-if="!messagesLoading && messages.length === 0" class="messages-empty">
            <el-empty description="暂无聊天记录，发送第一条消息吧" :image-size="80" />
          </div>
        </div>

        <!-- Input -->
        <div class="input-area">
          <div v-if="currentSession.chat_status === 2" class="ai-hint-bar">
            <el-icon><MagicStick /></el-icon>
            <span>AI正在自动跟进，您可以随时输入接管对话</span>
          </div>
          <div class="input-row">
            <el-input
              v-model="inputContent"
              type="textarea"
              :rows="2"
              :placeholder="currentSession.chat_status === 2 ? '输入消息将自动接管AI对话...' : '输入消息内容...'"
              resize="none"
              @keydown.enter.exact.prevent="handleSend"
            />
            <el-button
              type="primary"
              :loading="sendLoading"
              :disabled="!inputContent.trim()"
              @click="handleSend"
            >
              发送
            </el-button>
          </div>
        </div>
      </template>
      <template v-else>
        <div class="chat-empty">
          <el-icon :size="64" color="#c0c4cc"><ChatDotRound /></el-icon>
          <p>选择一个对话开始聊天</p>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Search, Loading, ChatDotRound, Check, WarningFilled, MagicStick } from '@element-plus/icons-vue'
import { getSessions, getMessages, sendMessage, getAvailableAccounts } from '@/api/chat'
import type { ChatSession, ChatMessage, DouyinAccount } from '@/api/chat'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const route = useRoute()

// ── Sessions ──
const sessions = ref<ChatSession[]>([])
const sessionsLoading = ref(false)
const searchText = ref('')
const currentLeadId = ref<number | null>(null)
const currentSession = computed(() => sessions.value.find(s => s.lead_id === currentLeadId.value) || null)

const filteredSessions = computed(() => {
  if (!searchText.value) return sessions.value
  const kw = searchText.value.toLowerCase()
  return sessions.value.filter(s =>
    (s.lead_nickname || '').toLowerCase().includes(kw) ||
    (s.lead_uid || '').toLowerCase().includes(kw)
  )
})

async function fetchSessions() {
  sessionsLoading.value = true
  try {
    const res = await getSessions()
    if (res.code === 200) {
      sessions.value = res.data || []
      // 如果URL中有lead_id参数，自动选中对应会话
      const queryLeadId = route.query.lead_id
      if (queryLeadId && !currentLeadId.value) {
        const targetId = Number(queryLeadId)
        const session = sessions.value.find(s => s.lead_id === targetId)
        if (session) {
          selectSession(session)
        }
      }
    }
  } finally {
    sessionsLoading.value = false
  }
}

function selectSession(session: ChatSession) {
  currentLeadId.value = session.lead_id
  session.unread_count = 0
  fetchMessages()
}

// ── Messages ──
const messages = ref<ChatMessage[]>([])
const messagesLoading = ref(false)
const messageAreaRef = ref<HTMLElement | null>(null)

async function fetchMessages() {
  if (!currentLeadId.value) return
  messagesLoading.value = true
  try {
    const res = await getMessages(currentLeadId.value, 1, 200)
    if (res.code === 200) {
      messages.value = res.data || []
      await nextTick()
      scrollToBottom()
    }
  } finally {
    messagesLoading.value = false
  }
}

function scrollToBottom() {
  if (messageAreaRef.value) {
    messageAreaRef.value.scrollTop = messageAreaRef.value.scrollHeight
  }
}

// ── Accounts ──
const availableAccounts = ref<DouyinAccount[]>([])
const selectedAccountId = ref<number | undefined>(undefined)

async function fetchAccounts() {
  try {
    const res = await getAvailableAccounts()
    if (res.code === 200) {
      availableAccounts.value = res.data || []
      if (availableAccounts.value.length > 0 && !selectedAccountId.value) {
        selectedAccountId.value = availableAccounts.value[0].id
      }
    }
  } catch {}
}

// ── Send ──
const inputContent = ref('')
const sendLoading = ref(false)

async function handleSend() {
  if (!inputContent.value.trim() || !currentLeadId.value) return
  if (availableAccounts.value.length === 0) {
    ElMessage.warning('没有可用的抖音账号，请联系管理员分配')
    return
  }

  sendLoading.value = true
  const contentToSend = inputContent.value.trim()
  try {
    const res = await sendMessage({
      lead_id: currentLeadId.value,
      content: contentToSend,
      douyin_account_id: selectedAccountId.value,
    })
    if (res.code === 200) {
      inputContent.value = ''
      // Add message to local list
      if (res.data?.message_id) {
        messages.value.push({
          id: res.data.message_id,
          lead_id: currentLeadId.value!,
          douyin_account_id: selectedAccountId.value!,
          direction: 'outbound',
          content: contentToSend,
          msg_type: 'text',
          sent_at: new Date().toISOString(),
          status: 'sent',
        })
        await nextTick()
        scrollToBottom()
      }
      // 如果从AI托管切换到人工，更新UI
      if (res.data?.switched_to_human) {
        const session = sessions.value.find(s => s.lead_id === currentLeadId.value)
        if (session) {
          session.chat_status = 1
        }
        ElMessage.success('已接管对话，切换为人工服务模式')
      }
      // Update session preview
      const session = sessions.value.find(s => s.lead_id === currentLeadId.value)
      if (session) {
        session.last_message = contentToSend
        session.last_message_at = new Date().toISOString()
      }
      if (res.data?.warning) {
        ElMessage.warning(res.data.warning)
      }
      // Refresh sessions to update order
      fetchSessions()
    } else {
      ElMessage.error(res.message || '发送失败')
    }
  } finally {
    sendLoading.value = false
  }
}

// ── WebSocket ──
let ws: WebSocket | null = null
let wsPingTimer: ReturnType<typeof setInterval> | null = null

function connectWebSocket() {
  const userId = userStore.userInfo?.id
  if (!userId) return

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsUrl = `${protocol}//${window.location.host}/api/v1/chat/ws/${userId}`
  ws = new WebSocket(wsUrl)

  ws.onopen = () => {
    wsPingTimer = setInterval(() => {
      if (ws?.readyState === WebSocket.OPEN) ws.send('ping')
    }, 30000)
  }

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.type === 'new_conversation') {
        // AI发起新对话，刷新会话列表
        fetchSessions()
        // 如果当前正在查看该线索，添加消息
        if (data.data?.lead_id === currentLeadId.value && data.data?.message) {
          messages.value.push(data.data.message)
          nextTick(() => scrollToBottom())
        }
      } else if (data.type === 'new_message' && data.data?.lead_id === currentLeadId.value) {
        // 添加新消息（AI回复或用户回复）
        messages.value.push(data.data)
        nextTick(() => scrollToBottom())
        // 如果是AI回复且当前会话不是AI托管，更新状态
        if (data.data.chat_status !== undefined) {
          const session = sessions.value.find(s => s.lead_id === currentLeadId.value)
          if (session) {
            session.chat_status = data.data.chat_status
          }
        }
        // 更新会话列表预览
        const session = sessions.value.find(s => s.lead_id === data.data.lead_id)
        if (session) {
          session.last_message = data.data.content
          session.last_message_at = new Date().toISOString()
        }
      } else if (data.type === 'new_message' && data.data?.lead_id !== currentLeadId.value) {
        // 其他会话的新消息，刷新列表以更新预览
        fetchSessions()
      }
    } catch {}
  }

  ws.onclose = () => {
    if (wsPingTimer) clearInterval(wsPingTimer)
    // Reconnect after 3s
    setTimeout(connectWebSocket, 3000)
  }
}

function disconnectWebSocket() {
  if (wsPingTimer) clearInterval(wsPingTimer)
  if (ws) {
    ws.close()
    ws = null
  }
}

// ── Helpers ──
function formatTime(dateStr: string | null) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  const now = new Date()
  if (d.toDateString() === now.toDateString()) {
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
}

function formatMessageTime(dateStr: string) {
  if (!dateStr) return ''
  return new Date(dateStr).toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  })
}

// ── Lifecycle ──
onMounted(() => {
  fetchSessions()
  fetchAccounts()
  connectWebSocket()
})

onUnmounted(() => {
  disconnectWebSocket()
})
</script>

<style scoped lang="scss">
.chat-container {
  display: flex;
  height: calc(100vh - 100px);
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

// ── Session panel ──
.session-panel {
  width: 320px;
  min-width: 280px;
  border-right: 1px solid #ebeef5;
  display: flex;
  flex-direction: column;
}

.session-header {
  padding: 16px;
  border-bottom: 1px solid #ebeef5;
}

.session-list {
  flex: 1;
  overflow-y: auto;
}

.session-item {
  display: flex;
  align-items: center;
  padding: 14px 16px;
  cursor: pointer;
  border-bottom: 1px solid #f5f5f5;
  transition: background 0.2s;

  &:hover { background: #f5f7fa; }
  &.active { background: #ecf5ff; }
}

.session-info {
  flex: 1;
  min-width: 0;
}

.session-top {
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;
}

.session-name {
  font-weight: 500;
  font-size: 14px;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-time {
  font-size: 12px;
  color: #909399;
  flex-shrink: 0;
  margin-left: 8px;
}

.session-bottom {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.session-preview {
  font-size: 13px;
  color: #909399;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.unread-badge {
  flex-shrink: 0;
  margin-left: 8px;
}

.intent-tag {
  flex-shrink: 0;
  margin-left: 4px;
}

.session-tags {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  flex-shrink: 0;
}

.chat-status-tag {
  flex-shrink: 0;
}

.session-loading, .session-empty {
  padding: 40px 0;
  text-align: center;
}

// ── Chat panel ──
.chat-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  border-bottom: 1px solid #ebeef5;
  background: #fafafa;
}

.chat-header-name {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.chat-header-uid {
  font-size: 12px;
  color: #909399;
  margin-left: 12px;
}

.chat-header-status {
  margin-left: 12px;
}

.chat-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #909399;
  gap: 16px;

  p { font-size: 16px; }
}

// ── Messages ──
.message-area {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.messages-loading {
  text-align: center;
  color: #909399;
  padding: 10px;
}

.messages-empty {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.message-row {
  display: flex;
  margin-bottom: 16px;

  &.outbound {
    justify-content: flex-end;
    .message-bubble {
      background: #409eff;
      color: #fff;
      border-radius: 12px 12px 2px 12px;
    }
    .message-time { color: rgba(255, 255, 255, 0.7); }
  }

  &.inbound {
    justify-content: flex-start;
    .message-bubble {
      background: #f0f2f5;
      color: #303133;
      border-radius: 12px 12px 12px 2px;
    }
    .message-time { color: #909399; }
  }
}

.message-bubble {
  max-width: 65%;
  padding: 10px 14px;
  word-break: break-word;
}

.message-ai-label {
  font-size: 11px;
  color: #e6a23c;
  display: flex;
  align-items: center;
  gap: 2px;
  margin-bottom: 4px;
}

.message-content {
  font-size: 14px;
  line-height: 1.5;
}

.message-meta {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
}

.message-time {
  font-size: 11px;
}

// ── Input ──
.input-area {
  display: flex;
  flex-direction: column;
  gap: 0;
  padding: 0;
  border-top: 1px solid #ebeef5;
  background: #fff;
}

.ai-hint-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 20px;
  background: #fdf6ec;
  color: #e6a23c;
  font-size: 13px;
  border-bottom: 1px solid #faecd8;
}

.input-row {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  padding: 16px 20px;
}

.input-row .el-textarea {
  flex: 1;
}
</style>
