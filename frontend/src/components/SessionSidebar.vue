<template>
  <aside class="session-sidebar" :class="{ 'mobile-open': mobileOpen }">
    <!-- 侧边栏头部 -->
    <div class="sidebar-header">
      <div class="sidebar-brand">
        <span class="brand-dot"></span>
        <span class="brand-text">DATA<span class="brand-vis">VIS</span></span>
      </div>
      <button class="btn-new-session" @click="handleNewSession">
        + 新建分析
      </button>
    </div>

    <!-- 会话列表 -->
    <div class="session-list" v-if="groupedSessions.length > 0">
      <div
        v-for="group in groupedSessions"
        :key="group.label"
        class="session-group"
      >
        <div class="group-label">{{ group.label }}</div>
        <div
          v-for="session in group.sessions"
          :key="session.session_id"
          class="session-item"
          :class="{ active: session.session_id === store.sessionId }"
          @click="handleSwitchSession(session.session_id)"
        >
          <div class="session-item-icon">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
            </svg>
          </div>
          <div class="session-item-content">
            <input
              v-if="editingId === session.session_id"
              class="rename-input"
              v-model="editName"
              @keydown.enter.prevent="confirmRename(session.session_id)"
              @keydown.escape.prevent="cancelRename"
              @blur="confirmRename(session.session_id)"
              @click.stop
              ref="renameInputRef"
            />
            <span
              v-else
              class="session-filename"
              @dblclick.stop="startRename(session)"
            >{{ getDisplayName(session) }}</span>
            <span class="session-meta">{{ session.row_count || 0 }} 行 · {{ session.dataset_count || 1 }} 数据集</span>
          </div>
          <button
            class="btn-delete-session"
            @click.stop="handleDeleteSession(session.session_id)"
            title="删除会话"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="3 6 5 6 21 6"/>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
            </svg>
          </button>
        </div>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-else class="empty-state">
      <div class="empty-icon">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
          <line x1="12" y1="18" x2="12" y2="12"/>
          <line x1="9" y1="15" x2="15" y2="15"/>
        </svg>
      </div>
      <p class="empty-title">暂无会话</p>
      <p class="empty-hint">上传数据文件开始分析</p>
    </div>

    <!-- 移动端遮罩 -->
    <div v-if="mobileOpen" class="mobile-overlay" @click="mobileOpen = false"></div>
  </aside>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { useAppStore } from '@/stores/app'
import { listSessions, deleteSession as deleteSessionApi, renameSession as renameSessionApi } from '@/api/client'

const store = useAppStore()
const sessions = ref([])
const mobileOpen = ref(false)
const editingId = ref(null)
const editName = ref('')
const renameInputRef = ref(null)

const emit = defineEmits(['newSession', 'sessionSwitched'])

// 按 created_at 时间分组
const groupedSessions = computed(() => {
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const yesterday = new Date(today.getTime() - 86400000)
  const weekAgo = new Date(today.getTime() - 7 * 86400000)

  const groups = [
    { label: '今天', sessions: [] },
    { label: '昨天', sessions: [] },
    { label: '近 7 天', sessions: [] },
    { label: '更早', sessions: [] }
  ]

  for (const session of sessions.value) {
    if (session.is_expired) continue
    const created = new Date(session.created_at)
    if (created >= today) groups[0].sessions.push(session)
    else if (created >= yesterday) groups[1].sessions.push(session)
    else if (created >= weekAgo) groups[2].sessions.push(session)
    else groups[3].sessions.push(session)
  }

  return groups.filter(g => g.sessions.length > 0)
})

// 显示名称：优先 session_name，再去扩展名
function getDisplayName(session) {
  if (session.session_name) return session.session_name
  const name = session.filename || ''
  return name.replace(/\.(csv|xlsx|xls|json|data|test)$/i, '') || name || '未命名'
}

// 双击开始重命名
function startRename(session) {
  editingId.value = session.session_id
  editName.value = getDisplayName(session)
  nextTick(() => {
    const input = renameInputRef.value
    if (input) {
      input.focus()
      input.select()
    }
  })
}

// 确认重命名
async function confirmRename(sessionId) {
  const name = editName.value.trim()
  if (!name || editingId.value !== sessionId) {
    editingId.value = null
    return
  }

  editingId.value = null
  try {
    await renameSessionApi(sessionId, name)
    // 更新本地列表
    const s = sessions.value.find(s => s.session_id === sessionId)
    if (s) s.session_name = name
  } catch (e) {
    store.setError(e.message)
  }
}

// 取消重命名
function cancelRename() {
  editingId.value = null
}

async function fetchSessions() {
  try {
    const result = await listSessions()
    if (result.success) {
      sessions.value = result.sessions || []
    }
  } catch (e) {
    // 静默处理
  }
}

function handleNewSession() {
  emit('newSession')
  mobileOpen.value = false
}

async function handleSwitchSession(sessionId) {
  if (sessionId === store.sessionId) return
  emit('sessionSwitched', sessionId)
  mobileOpen.value = false
}

async function handleDeleteSession(sessionId) {
  if (!confirm('确定要删除此会话吗？所有数据将被清除。')) return
  try {
    await deleteSessionApi(sessionId)
    sessions.value = sessions.value.filter(s => s.session_id !== sessionId)
    if (store.sessionId === sessionId) {
      store.clearSession()
      store.setCharts([])
    }
  } catch (e) {
    store.setError(e.message)
  }
}

function toggleMobile() {
  mobileOpen.value = !mobileOpen.value
}

defineExpose({ fetchSessions, toggleMobile })

onMounted(() => fetchSessions())
</script>

<style scoped>
.session-sidebar {
  width: 260px;
  background: var(--theme-dark);
  border-right: 1px solid var(--theme-border);
  display: flex;
  flex-direction: column;
  height: 100vh;
  position: sticky;
  top: 0;
  flex-shrink: 0;
  overflow: hidden;
}

/* 头部 */
.sidebar-header {
  padding: 1rem;
  border-bottom: 1px solid var(--theme-border);
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.brand-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--theme-green);
  box-shadow: 0 0 8px var(--theme-green);
  animation: pulse-dot 2s ease-in-out infinite;
}

@keyframes pulse-dot {
  0%, 100% { box-shadow: 0 0 8px var(--theme-green); }
  50% { box-shadow: 0 0 16px var(--theme-green), 0 0 32px rgba(23, 247, 0, 0.2); }
}

.brand-text {
  font-size: 1rem;
  font-weight: 700;
  letter-spacing: 0.15em;
  color: transparent;
  -webkit-text-stroke: 1px var(--theme-white);
}

.brand-vis {
  color: var(--theme-green);
  -webkit-text-stroke: 0;
}

.btn-new-session {
  width: 100%;
  padding: 0.6rem;
  background: transparent;
  border: 1px solid var(--theme-green);
  color: var(--theme-green);
  border-radius: var(--theme-radius-sm);
  font-size: 0.85rem;
  font-weight: 600;
  letter-spacing: 0.05em;
  cursor: pointer;
  transition: var(--theme-transition);
}

.btn-new-session:hover {
  background: var(--theme-green);
  color: var(--theme-black);
}

/* 会话列表 */
.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 0.5rem;
}

.session-list::-webkit-scrollbar {
  width: 4px;
}

.session-list::-webkit-scrollbar-thumb {
  background: var(--theme-border);
  border-radius: 2px;
}

.session-group {
  margin-bottom: 0.5rem;
}

.group-label {
  font-size: 0.7rem;
  color: var(--theme-white-dim);
  text-transform: uppercase;
  letter-spacing: 0.15em;
  padding: 0.5rem 0.5rem 0.25rem;
  font-weight: 500;
}

/* 会话条目 */
.session-item {
  display: flex;
  align-items: center;
  padding: 0.6rem 0.75rem;
  border-radius: var(--theme-radius-sm);
  cursor: pointer;
  transition: var(--theme-transition);
  border: 1px solid transparent;
  gap: 0.5rem;
}

.session-item:hover {
  background: var(--theme-dark-2);
}

.session-item.active {
  background: var(--theme-green-dim);
  border-color: rgba(23, 247, 0, 0.3);
}

.session-item-icon {
  flex-shrink: 0;
  color: var(--theme-white-dim);
  display: flex;
  align-items: center;
  justify-content: center;
}

.session-item.active .session-item-icon {
  color: var(--theme-green);
}

.session-item-content {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  min-width: 0;
  flex: 1;
}

.session-filename {
  font-size: 0.85rem;
  color: var(--theme-white);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
}

.session-filename:hover {
  opacity: 0.8;
}

.rename-input {
  font-size: 0.85rem;
  color: var(--theme-white);
  font-weight: 500;
  background: var(--theme-dark-2);
  border: 1px solid var(--theme-green);
  border-radius: 3px;
  padding: 1px 4px;
  outline: none;
  width: 100%;
  font-family: inherit;
  box-sizing: border-box;
}

.session-item.active .session-filename {
  color: var(--theme-green);
}

.session-meta {
  font-size: 0.7rem;
  color: var(--theme-white-dim);
}

/* 删除按钮 */
.btn-delete-session {
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  color: var(--theme-red);
  border-radius: 4px;
  cursor: pointer;
  flex-shrink: 0;
  opacity: 0;
  transition: var(--theme-transition);
  display: flex;
  align-items: center;
  justify-content: center;
}

.session-item:hover .btn-delete-session {
  opacity: 0.7;
}

.btn-delete-session:hover {
  opacity: 1 !important;
  background: rgba(255, 68, 68, 0.1);
}

/* 空状态 */
.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem;
  gap: 0.5rem;
}

.empty-icon {
  color: var(--theme-border);
  margin-bottom: 0.5rem;
}

.empty-title {
  margin: 0;
  font-size: 0.9rem;
  color: var(--theme-white-dim);
}

.empty-hint {
  margin: 0;
  font-size: 0.75rem;
  color: var(--theme-white-dim);
  opacity: 0.6;
}

/* 移动端遮罩 */
.mobile-overlay {
  display: none;
}

/* 移动端 */
@media (max-width: 768px) {
  .session-sidebar {
    position: fixed;
    left: -260px;
    top: 0;
    z-index: 100;
    transition: left 0.3s ease;
    box-shadow: none;
  }

  .session-sidebar.mobile-open {
    left: 0;
    box-shadow: 4px 0 20px rgba(0, 0, 0, 0.5);
  }

  .mobile-overlay {
    display: block;
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    z-index: 99;
  }
}
</style>
