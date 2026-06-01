import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.mount('#app')

// 恢复状态
import { useAppStore } from './stores/app'
const store = useAppStore()
store.$hydrate()
