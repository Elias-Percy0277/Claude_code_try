<template>
  <div class="chat-panel">
    <div class="messages" ref="messagesContainer">
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
          <div class="message-text" v-if="message.content">{{ message.content }}</div>

          <!-- Agent2 建议卡片 -->
          <div v-if="message.suggestions && message.suggestions.length > 0" class="suggestions-panel">
            <div class="suggestions-title">分析建议</div>
            <div class="suggestion-card" v-for="(s, si) in message.suggestions" :key="si">
              <div class="suggestion-header">
                <span class="suggestion-title">{{ s.title }}</span>
                <span class="suggestion-op">{{ s.operation }}</span>
              </div>
              <div class="suggestion-rationale">{{ s.rationale }}</div>
              <div class="suggestion-expected">{{ s.expected_insight }}</div>
              <button class="btn-adopt" @click.stop="$emit('adoptSuggestion', s)" :disabled="store.isLoading">
                一键执行
              </button>
            </div>
          </div>

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

      <!-- 加载中指示器 -->
      <div v-if="store.isLoading" class="message assistant">
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
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import { useAppStore } from '@/stores/app'

const store = useAppStore()
const messagesContainer = ref(null)

const emit = defineEmits(['viewCharts', 'pinCharts', 'adoptSuggestion'])

function handleViewCharts(messageIndex) {
  emit('viewCharts', messageIndex)
}

function handlePinCharts(messageIndex) {
  emit('pinCharts', messageIndex)
}

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

function scrollToBottom() {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
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
  max-height: 80vh;
  height: 400px;
  resize: vertical;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.messages {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  overflow-y: auto;
  flex: 1;
  padding-right: 4px;
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

/* ============ 建议卡片 ============ */
.suggestions-panel {
  margin-top: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.suggestions-title {
  font-size: 0.8rem;
  color: var(--theme-green);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.suggestion-card {
  background: var(--theme-dark-2);
  border: 1px solid var(--theme-border);
  border-radius: var(--theme-radius-sm);
  padding: 0.6rem 0.8rem;
  transition: var(--theme-transition);
}

.suggestion-card:hover {
  border-color: rgba(23, 247, 0, 0.3);
}

.suggestion-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.3rem;
}

.suggestion-title {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--theme-white);
}

.suggestion-op {
  font-size: 0.7rem;
  padding: 0.15rem 0.5rem;
  border-radius: 10px;
  background: var(--theme-green-dim);
  color: var(--theme-green);
  border: 1px solid rgba(23, 247, 0, 0.2);
}

.suggestion-rationale {
  font-size: 0.78rem;
  color: var(--theme-white-dim);
  margin-bottom: 0.2rem;
}

.suggestion-expected {
  font-size: 0.72rem;
  color: var(--theme-white-dim);
  opacity: 0.7;
  margin-bottom: 0.5rem;
}

.btn-adopt {
  padding: 0.3rem 0.8rem;
  background: transparent;
  color: var(--theme-green);
  border: 1px solid var(--theme-green);
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.75rem;
  font-weight: 500;
  transition: var(--theme-transition);
}

.btn-adopt:hover:not(:disabled) {
  background: var(--theme-green);
  color: var(--theme-black);
}

.btn-adopt:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}
</style>
