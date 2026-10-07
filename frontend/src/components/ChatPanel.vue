<template>
  <div class="chat-panel">
    <div class="messages" ref="messagesContainer" @scroll="onScroll">
      <div
        v-for="(message, index) in store.messages"
        :key="index"
        class="message"
        :class="message.role"
      >
        <div class="message-avatar" :class="message.role">
          <span v-if="message.role === 'user'">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <circle cx="8" cy="5" r="3" stroke="currentColor" stroke-width="1.2"/>
              <path d="M2 15C2 11.134 4.68629 8 8 8C11.3137 8 14 11.134 14 15" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
            </svg>
          </span>
          <span v-else-if="message.role === 'system'">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.2"/>
              <path d="M8 5V8L10 10" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
            </svg>
          </span>
          <span v-else>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <rect x="2" y="3" width="12" height="9" rx="2" stroke="currentColor" stroke-width="1.2"/>
              <circle cx="5.5" cy="7.5" r="1" fill="currentColor"/>
              <circle cx="8" cy="7.5" r="1" fill="currentColor"/>
              <circle cx="10.5" cy="7.5" r="1" fill="currentColor"/>
            </svg>
          </span>
        </div>
        <div class="message-content">
          <div
            v-if="message.content"
            class="message-text"
            :class="{
              'md-render': message.role === 'assistant' && !isProgressMessage(message),
              'progress-text': isProgressMessage(message)
            }"
            v-html="renderContent(message, index)"
          ></div>

          <div v-if="message.charts && message.charts.length > 0" class="message-charts">
            <button
              class="charts-count-btn"
              :class="{ active: isViewingThisCharts(index) }"
              @click.stop="handleViewCharts(index)"
              :title="isViewingThisCharts(index) ? '正在查看此图表' : '点击查看图表'"
            >
              {{ message.charts.length }} 个图表
              <span v-if="isViewingThisCharts(index)" class="viewing-badge">查看中</span>
            </button>
            <button
              class="charts-pin-btn"
              @click.stop="handlePinCharts(index)"
              title="固定图表用于对比"
            >
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                <path d="M6 1V11M3 4L6 1L9 4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
              固定对比
            </button>
          </div>
        </div>
      </div>

      <!-- 加载中指示器：仅在等待首个数据到达时显示 -->
      <div v-if="store.isLoading && !isLastAssistantStreaming" class="message assistant">
        <div class="message-avatar assistant">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <rect x="2" y="3" width="12" height="9" rx="2" stroke="currentColor" stroke-width="1.2"/>
            <circle cx="5.5" cy="7.5" r="1" fill="currentColor"/>
            <circle cx="8" cy="7.5" r="1" fill="currentColor"/>
            <circle cx="10.5" cy="7.5" r="1" fill="currentColor"/>
          </svg>
        </div>
        <div class="message-content">
          <div class="typing-indicator">
            <span></span>
            <span></span>
            <span></span>
          </div>
        </div>
      </div>
    </div>
    <!-- 跳转按钮 -->
    <button
      v-if="showJump"
      class="jump-btn"
      @click="handleJump"
      :title="isNearBottom ? '跳转到顶部' : '跳转到底部'"
    >
      <svg v-if="isNearBottom" width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path d="M8 12V4M8 4L4 8M8 4L12 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      <svg v-else width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path d="M8 4V12M8 12L4 8M8 12L12 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </button>
  </div>
</template>

<script setup>
// ============================================================
// 组件职责：ChatPanel —— 聊天面板
// 负责：渲染对话消息列表（用户/助手/系统），支持 Markdown 渲染、
// 流式接收期间的纯文本降级显示、进度消息（⏳ 前缀）的特殊样式、
// 图表查看/固定按钮的事件抛出，以及消息滚动、跳转按钮等交互。
// ============================================================
import { ref, computed, watch, nextTick } from 'vue'
import { useAppStore } from '@/stores/app'
import { marked } from 'marked'

const store = useAppStore()
const messagesContainer = ref(null)

const emit = defineEmits(['viewCharts', 'pinCharts'])

marked.setOptions({
  breaks: true,
  gfm: true,
})

// 判断最后一条助手消息是否正在流式接收中（有内容且不是纯进度消息）
// AI-assisted: 使用 Claude 实现流式状态判断计算属性，未做大幅修改
const isLastAssistantStreaming = computed(() => {
  if (!store.isLoading || store.messages.length === 0) return false
  const lastMsg = store.messages[store.messages.length - 1]
  return lastMsg?.role === 'assistant' && lastMsg.content?.length > 0 && !lastMsg.content.startsWith('⏳')
})

// 流式传输期间跳过 Markdown 解析，避免主线程阻塞
// AI-assisted: 使用 Claude 实现 Markdown 渲染与流式拼接，手动调整了流式期间转义与滚动行为
function renderContent(message, index) {
  if (message.role === 'assistant') {
    // 进度消息：直接转义显示
    if (isProgressMessage(message)) {
      return message.content
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
    }
    // 正在流式接收的最后一条消息：直接显示纯文本
    const isStreaming = store.isLoading &&
      index === store.messages.length - 1 &&
      message.content.length > 0
    if (isStreaming) {
      // 转义 HTML 特殊字符后显示纯文本，保留换行
      return message.content
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\n/g, '<br>')
    }
    return marked.parse(message.content)
  }
  return message.content
}

// 判断消息是否是进度消息
// AI-assisted: 使用 Claude 实现进度消息识别，未做大幅修改
function isProgressMessage(message) {
  return message.role === 'assistant' &&
    store.isLoading &&
    message.content?.startsWith('⏳')
}

// 查看该消息关联的图表，向父组件抛出 viewCharts 事件
// AI-assisted: 使用 Claude 实现查看图表事件抛出，未做大幅修改
function handleViewCharts(messageIndex) {
  emit('viewCharts', messageIndex)
}

// 固定该消息关联的图表用于对比，向父组件抛出 pinCharts 事件
// AI-assisted: 使用 Claude 实现固定对比事件抛出，未做大幅修改
function handlePinCharts(messageIndex) {
  emit('pinCharts', messageIndex)
}

// 判断当前是否正在查看该消息的图表（用于高亮查看中按钮）
// AI-assisted: 使用 Claude 实现查看状态判断，未做大幅修改
function isViewingThisCharts(messageIndex) {
  return store.viewingHistoryCharts && store.viewingMessageIndex === messageIndex
}

watch(() => store.messages.length, async () => {
  await nextTick()
  scrollToBottom()
})

watch(() => store.charts.length, async () => {
  await nextTick()
  scrollToBottom()
})

// 监听流式内容变化，自动滚动到底部
watch(() => {
  if (store.messages.length === 0) return 0
  const lastMsg = store.messages[store.messages.length - 1]
  return lastMsg?.content?.length || 0
}, async () => {
  if (store.isLoading) {
    await nextTick()
    scrollToBottom()
  }
})

// 将消息容器滚动到底部
// AI-assisted: 使用 Claude 实现滚动到底部，未做大幅修改
function scrollToBottom() {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

const showJump = ref(false)
const isNearBottom = ref(true)

// 滚动监听：根据位置决定跳转按钮显隐，并记录是否处于底部附近
// AI-assisted: 使用 Claude 实现滚动监听与跳转按钮显隐，未做大幅修改
function onScroll() {
  const el = messagesContainer.value
  if (!el) return
  const threshold = 100
  showJump.value = el.scrollHeight > el.clientHeight + threshold
  isNearBottom.value = el.scrollTop + el.clientHeight >= el.scrollHeight - threshold
}

// 跳转按钮：靠近底部时跳到顶部，否则平滑滚动到底部
// AI-assisted: 使用 Claude 实现跳转顶部/底部逻辑，未做大幅修改
function handleJump() {
  const el = messagesContainer.value
  if (!el) return
  if (isNearBottom.value) {
    el.scrollTo({ top: 0, behavior: 'smooth' })
  } else {
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }
}
</script>

<style scoped>
.chat-panel {
  background: var(--theme-dark);
  border: 1px solid var(--theme-border);
  border-radius: var(--theme-radius);
  padding: 1rem;
  min-height: 200px;
  flex: 1;
  resize: vertical;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  position: relative;
}

.messages {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  overflow-y: auto;
  flex: 1;
  padding-right: 4px;
}

/* 跳转按钮 */
.jump-btn {
  position: absolute;
  right: 1.5rem;
  bottom: 1.5rem;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 1px solid var(--theme-green);
  background: var(--theme-green);
  color: var(--theme-black);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 5;
  opacity: 0.85;
  transition: opacity 0.2s, box-shadow 0.2s;
}

.jump-btn:hover {
  opacity: 1;
  box-shadow: 0 0 12px rgba(0, 255, 65, 0.4);
}

.message {
  display: flex;
  gap: 0.75rem;
}

.message.user {
  flex-direction: row-reverse;
}

.message-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.message-avatar.user {
  background: var(--theme-green);
  color: var(--theme-black);
}

.message-avatar.assistant {
  background: var(--theme-dark-2);
  border: 1px solid var(--theme-border);
  color: var(--theme-green);
}

.message-avatar.system {
  background: var(--theme-dark-2);
  border: 1px solid var(--theme-border);
  color: var(--theme-green);
}

.message-content {
  max-width: 80%;
  min-width: 0;
}

.message-text {
  padding: 0.75rem 1rem;
  border-radius: var(--theme-radius-sm);
  line-height: 1.6;
  white-space: pre-wrap;
  font-size: 0.9rem;
  word-break: break-word;
}

.message-text.md-render {
  white-space: normal;
}

/* Markdown 表格样式 */
.message-text.md-render :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 0.75rem 0;
  font-size: 0.82rem;
}

.message-text.md-render :deep(th) {
  background: rgba(23, 247, 0, 0.1);
  color: var(--theme-green);
  font-weight: 600;
  text-align: left;
  padding: 0.5rem 0.65rem;
  border: 1px solid var(--theme-border);
  white-space: nowrap;
}

.message-text.md-render :deep(td) {
  padding: 0.45rem 0.65rem;
  border: 1px solid var(--theme-border);
  color: var(--theme-white);
}

.message-text.md-render :deep(tr:nth-child(even)) {
  background: rgba(255, 255, 255, 0.03);
}

.message-text.md-render :deep(tr:hover) {
  background: rgba(23, 247, 0, 0.05);
}

/* Markdown 其他元素 */
.message-text.md-render :deep(h2) {
  color: var(--theme-green);
  font-size: 1.1rem;
  margin: 1rem 0 0.5rem;
  border-bottom: 1px solid var(--theme-border);
  padding-bottom: 0.3rem;
}

.message-text.md-render :deep(h3) {
  color: var(--theme-green);
  font-size: 0.95rem;
  margin: 0.8rem 0 0.4rem;
}

.message-text.md-render :deep(strong) {
  color: var(--theme-green);
}

.message-text.md-render :deep(ul),
.message-text.md-render :deep(ol) {
  padding-left: 1.2rem;
  margin: 0.4rem 0;
}

.message-text.md-render :deep(li) {
  margin: 0.2rem 0;
}

.message-text.md-render :deep(code) {
  background: rgba(255, 255, 255, 0.08);
  padding: 0.1rem 0.35rem;
  border-radius: 3px;
  font-size: 0.85em;
}

.message.user .message-text {
  background: var(--theme-green);
  color: var(--theme-black);
  border-bottom-right-radius: 2px;
  font-weight: 500;
}

.message.assistant .message-text {
  background: var(--theme-dark-2);
  color: var(--theme-white);
  border-bottom-left-radius: 2px;
  border: 1px solid var(--theme-border);
}

/* 进度消息样式 */
.message.assistant .progress-text {
  background: transparent;
  border: 1px dashed var(--theme-border);
  color: var(--theme-green);
  font-size: 0.85rem;
  padding: 0.5rem 0.85rem;
  animation: progress-pulse 2s ease-in-out infinite;
}

@keyframes progress-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

.message.system .message-text {
  background: var(--theme-green-dim);
  border-left: 2px solid var(--theme-green);
  color: var(--theme-white);
  font-size: 0.85rem;
}

.message-charts {
  margin-top: 0.5rem;
}

.charts-count-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.4rem 0.8rem;
  background: transparent;
  border: 1px solid var(--theme-green);
  border-radius: 4px;
  font-size: 0.85rem;
  color: var(--theme-green);
  cursor: pointer;
  transition: var(--theme-transition);
}

.charts-count-btn:hover {
  background: var(--theme-green);
  color: var(--theme-black);
}

.charts-count-btn.active {
  background: var(--theme-green);
  color: var(--theme-black);
}

.viewing-badge {
  font-size: 0.7rem;
  background: rgba(0, 0, 0, 0.2);
  padding: 0.1rem 0.4rem;
  border-radius: 3px;
}

.charts-pin-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.4rem 0.7rem;
  background: transparent;
  border: 1px solid #ffd93d;
  border-radius: 4px;
  font-size: 0.8rem;
  color: #ffd93d;
  cursor: pointer;
  transition: var(--theme-transition);
}

.charts-pin-btn:hover {
  background: #ffd93d;
  color: var(--theme-black);
}

/* 加载动画 */
.typing-indicator {
  display: flex;
  gap: 5px;
  padding: 0.75rem 1rem;
  background: var(--theme-dark-2);
  border: 1px solid var(--theme-border);
  border-radius: var(--theme-radius-sm);
  width: fit-content;
}

.typing-indicator span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--theme-green);
  animation: typing 1.4s ease-in-out infinite;
}

.typing-indicator span:nth-child(2) {
  animation-delay: 0.2s;
}

.typing-indicator span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes typing {
  0%, 60%, 100% {
    transform: translateY(0);
    opacity: 0.4;
  }
  30% {
    transform: translateY(-6px);
    opacity: 1;
  }
}
</style>
