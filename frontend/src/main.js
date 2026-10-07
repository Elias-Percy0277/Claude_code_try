/**
 * main.js 应用入口
 * 职责：创建 Vue 应用实例并挂载 Pinia 状态管理，启动后从 localStorage 恢复上次会话状态。
 */
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.mount('#app')

// 恢复状态
// AI-assisted: 使用 Claude 实现应用启动后的状态恢复调用，未做大幅修改
import { useAppStore } from './stores/app'
const store = useAppStore()
store.$hydrate()
