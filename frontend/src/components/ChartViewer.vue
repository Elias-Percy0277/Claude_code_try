<template>
  <div class="chart-viewer">
    <div class="chart-title-row">
      <h3 class="chart-title">
        <span class="title-dot"></span>
        {{ props.historyMode ? '历史图表' : '分析图表' }}
      </h3>
      <button class="btn-close-charts" @click="handleCloseCharts" title="关闭图表">
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
          <path d="M2 2L12 12M12 2L2 12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
      </button>
    </div>

    <div
      class="charts-container"
    >
      <div
        v-for="(item, index) in allCharts"
        :key="item.uid"
        class="chart-item"
        :class="{
          'chart-pinned': item.pinned
        }"
      >
        <!-- 图表标题栏 -->
        <div
          class="chart-header"
        >
          <span
            class="chart-label"
            :class="{ 'pinned-label': item.pinned }"
            contenteditable="true"
            @blur="handleTitleBlur(index, $event)"
            @keydown.enter.prevent="$event.target.blur()"
          >{{ getChartTitle(item.chart) }}</span>
          <div class="chart-header-btns">
            <button
              v-if="item.pinned"
              class="header-btn"
              @click="unpinChart(index)"
              title="取消固定"
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M3 3L11 11M11 3L3 11" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
              </svg>
            </button>
            <button
              class="settings-toggle"
              :class="{ active: panelStates[index]?.open }"
              @click.stop="togglePanel(index)"
              title="图表设置"
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <circle cx="7" cy="7" r="1.5" stroke="currentColor" stroke-width="1"/>
                <path d="M7 1V2.5M7 11.5V13M1 7H2.5M11.5 7H13M2.8 2.8L3.9 3.9M10.1 10.1L11.2 11.2M11.2 2.8L10.1 3.9M3.9 10.1L2.8 11.2" stroke="currentColor" stroke-width="1" stroke-linecap="round"/>
              </svg>
            </button>
          </div>
        </div>

        <!-- 可折叠设置面板 -->
        <div class="settings-panel" :class="{ open: panelStates[index]?.open }">
          <!-- 坐标轴标签 -->
          <div class="setting-row" v-if="hasYAxis(item.chart)">
            <label class="setting-label">轴标签</label>
            <div class="setting-inputs">
              <input
                type="text"
                class="setting-input axis-name-input"
                :value="panelStates[index]?.xAxisName ?? getAxisName(item.chart, 'x')"
                @input="updatePanelState(index, 'xAxisName', $event.target.value)"
                placeholder="X 轴"
              />
              <span class="setting-sep">/</span>
              <input
                type="text"
                class="setting-input axis-name-input"
                :value="panelStates[index]?.yAxisName ?? getAxisName(item.chart, 'y')"
                @input="updatePanelState(index, 'yAxisName', $event.target.value)"
                placeholder="Y 轴"
              />
              <button class="btn-sm" @click="applyAxisNames(index)">应用</button>
            </div>
          </div>

          <!-- X 轴间距 -->
          <div class="setting-row" v-if="hasYAxis(item.chart)">
            <label class="setting-label">X 轴间距</label>
            <div class="setting-inputs">
              <input
                type="number"
                class="setting-input"
                min="0"
                :value="panelStates[index]?.xInterval ?? ''"
                @input="updatePanelState(index, 'xInterval', $event.target.value)"
                placeholder="间距值"
              />
              <button class="btn-sm" @click="applyXInterval(index)">应用</button>
              <button class="btn-sm btn-secondary" @click="resetXInterval(index)">重置</button>
            </div>
          </div>

          <!-- Y 轴范围 -->
          <div class="setting-row" v-if="hasYAxis(item.chart)">
            <label class="setting-label">Y 轴范围</label>
            <div class="setting-inputs">
              <input
                type="number"
                class="setting-input"
                :value="panelStates[index]?.yMin ?? ''"
                @input="updatePanelState(index, 'yMin', $event.target.value)"
                placeholder="最小"
              />
              <span class="setting-sep">~</span>
              <input
                type="number"
                class="setting-input"
                :value="panelStates[index]?.yMax ?? ''"
                @input="updatePanelState(index, 'yMax', $event.target.value)"
                placeholder="最大"
              />
              <button class="btn-sm" @click="applyYAxis(index)">应用</button>
              <button class="btn-sm btn-secondary" @click="resetYAxis(index)">重置</button>
            </div>
          </div>

          <!-- 图表类型切换 -->
          <div class="setting-row">
            <label class="setting-label">图表类型</label>
            <div class="setting-btns">
              <button
                v-for="t in chartTypes"
                :key="t.value"
                class="btn-type"
                :class="{ active: panelStates[index]?.chartType === t.value }"
                @click="switchType(index, t.value)"
              >{{ t.label }}</button>
            </div>
          </div>

          <!-- 数据标签 + 平滑 -->
          <div class="setting-row">
            <label class="setting-label">选项</label>
            <div class="setting-toggles">
              <label class="toggle-label" v-if="hasYAxis(item.chart)">
                <input
                  type="checkbox"
                  :checked="panelStates[index]?.showLabels"
                  @change="toggleLabels(index)"
                />
                <span>数据标签</span>
              </label>
              <label class="toggle-label" v-if="isLineLike(item.chart)">
                <input
                  type="checkbox"
                  :checked="panelStates[index]?.smooth"
                  @change="toggleSmooth(index)"
                />
                <span>平滑曲线</span>
              </label>
            </div>
          </div>

          <!-- 配色方案 -->
          <div class="setting-row">
            <label class="setting-label">配色</label>
            <div class="setting-btns">
              <button
                v-for="(theme, name) in COLOR_THEMES"
                :key="name"
                class="btn-theme"
                :class="{ active: panelStates[index]?.colorTheme === name }"
                @click="switchColorTheme(index, name)"
              >
                <span
                  v-for="(c, i) in theme.slice(0, 4)"
                  :key="i"
                  class="color-dot"
                  :style="{ background: c }"
                ></span>
              </button>
            </div>
          </div>
        </div>

        <!-- ECharts 图表容器 -->
        <div
          :ref="el => setChartRef(el, index)"
          class="echarts-chart"
          :style="{ height: getChartHeight(item.chart) }"
        ></div>

        <!-- 加载遮罩 -->
        <div v-if="loadingIndex === index" class="chart-loading">
          <div class="loading-spinner"></div>
          <span class="loading-text">切换中...</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
// ============================================================
// 组件职责：ChartViewer —— 图表渲染与交互中心
// 负责：基于 ECharts 渲染分析图表/历史图表，管理 ECharts 实例的
// 初始化、销毁、resize；提供图表设置面板（坐标轴标签、Y 轴范围、
// X 轴间距、图表类型切换、数据标签、平滑曲线、配色方案、标题编辑、
// 固定/取消固定）等可交互能力，并同步当前图表与固定图表的合并展示。
// ============================================================
import { ref, reactive, computed, onMounted, nextTick, watch, onUnmounted } from 'vue'
import { useAppStore } from '@/stores/app'
import * as echarts from 'echarts'
import { rechart as rechartAPI } from '@/api/client'

const props = defineProps({
  historyMode: {
    type: Boolean,
    default: false
  }
})

const store = useAppStore()
const chartRefs = ref([])
const chartInstances = ref([])
const resizeHandlers = ref([])

// 每个图表的控制面板状态
const panelStates = reactive({})

// 正在切换类型的图表索引（用于加载动画）
const loadingIndex = ref(-1)


// 标志位：前端切换类型时跳过 watch 重渲染
let skipNextWatch = false


// 合并当前图表 + 固定图表为一个统一列表
// AI-assisted: 使用 Claude 实现当前图表与固定图表的合并计算属性，人工校验后保留原逻辑
const allCharts = computed(() => {
  const result = []
  store.charts.forEach((chart, i) => {
    result.push({
      uid: `current-${i}`,
      chart,
      pinned: false
    })
  })
  store.pinnedCharts.forEach((chart, i) => {
    result.push({
      uid: `pinned-${i}`,
      chart,
      pinned: true
    })
  })
  return result
})

// 配色方案
const COLOR_THEMES = {
  classic: ['#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de', '#3ba272'],
  neon: ['#00f7ff', '#00ff41', '#ff6b6b', '#ffd93d', '#c084fc', '#fb923c'],
  warm: ['#ff6b6b', '#ffd93d', '#6bcb77', '#4d96ff', '#ff922b', '#845ef7']
}

// 可切换的图表类型
const chartTypes = [
  { value: 'bar', label: '柱状' },
  { value: 'line', label: '折线' },
  { value: 'area', label: '面积' },
  { value: 'pie', label: '饼图' },
  { value: 'radar', label: '雷达' },
  { value: 'scatter', label: '散点' }
]

// ECharts 暗色基础配置
const darkBaseOption = {
  backgroundColor: 'transparent',
  textStyle: { color: '#f7f7f7', fontFamily: 'Inter, sans-serif' },
  title: { textStyle: { color: '#f7f7f7' }, subtextStyle: { color: '#999' } },
  legend: { textStyle: { color: '#999' } },
  tooltip: {
    backgroundColor: 'rgba(26, 26, 26, 0.95)',
    borderColor: '#333',
    textStyle: { color: '#f7f7f7' }
  },
  xAxis: {
    axisLine: { lineStyle: { color: '#333' } },
    axisLabel: { color: '#999' },
    splitLine: { lineStyle: { color: '#222' } },
    nameTextStyle: { color: '#999' }
  },
  yAxis: {
    axisLine: { lineStyle: { color: '#333' } },
    axisLabel: { color: '#999' },
    splitLine: { lineStyle: { color: '#222' } },
    nameTextStyle: { color: '#999' }
  }
}

// 判断图表类型是否含有笛卡尔坐标轴（饼图/雷达/热力图除外）
// AI-assisted: 使用 Claude 实现图表类型判断工具函数，人工校验后保留原逻辑
function hasYAxis(chart) {
  const t = (chart.chart_type || '').toLowerCase()
  return !['pie', 'radar', 'heatmap'].includes(t)
}

// 判断图表是否为折线类（折线/面积），用于控制平滑曲线开关的显隐
// AI-assisted: 使用 Claude 实现折线类图表判断，未做大幅修改
function isLineLike(chart) {
  const t = (chart.chart_type || '').toLowerCase()
  return ['line', 'area'].includes(t)
}

// 获取图表标题，缺省返回 '图表'
// AI-assisted: 使用 Claude 实现图表标题读取，未做大幅修改
function getChartTitle(chart) {
  return chart.option?.title?.text || '图表'
}

// 收集每个图表的 DOM 容器引用，供 ECharts 初始化使用
// AI-assisted: 使用 Claude 实现 ref 回调收集图表容器，未做大幅修改
function setChartRef(el, index) {
  if (el) chartRefs.value[index] = el
}

// 根据图表类型返回容器高度（热力图/饼图更高，其余默认）
// AI-assisted: 使用 Claude 实现图表高度自适应，未做大幅修改
function getChartHeight(chart) {
  const type = chart.chart_type
  if (type === 'heatmap' || type === 'pie') return '400px'
  return '300px'
}


// 将暗色基础配置深合并到原始 option 中，补齐缺失的暗色样式字段
// AI-assisted: 使用 Claude 实现暗色主题深合并逻辑，手动调整了 tooltip 字段合并细节
function mergeDarkOption(originalOption) {
  const merged = JSON.parse(JSON.stringify(originalOption))
  for (const key of Object.keys(darkBaseOption)) {
    if (!merged[key]) {
      merged[key] = JSON.parse(JSON.stringify(darkBaseOption[key]))
    } else if (typeof darkBaseOption[key] === 'object' && typeof merged[key] === 'object') {
      for (const subKey of Object.keys(darkBaseOption[key])) {
        if (merged[key][subKey] === undefined) {
          merged[key][subKey] = darkBaseOption[key][subKey]
        }
      }
    }
  }
  if (!merged.tooltip) {
    merged.tooltip = darkBaseOption.tooltip
  } else {
    merged.tooltip.backgroundColor = merged.tooltip.backgroundColor || darkBaseOption.tooltip.backgroundColor
    merged.tooltip.borderColor = merged.tooltip.borderColor || darkBaseOption.tooltip.borderColor
    if (!merged.tooltip.textStyle) merged.tooltip.textStyle = darkBaseOption.tooltip.textStyle
  }
  return merged
}

// 增强 option：注入工具栏（缩放/还原/保存图片）与 Y 轴滑动 dataZoom
// AI-assisted: 使用 Claude 实现 toolbox 与 dataZoom 增强，人工校验后保留原逻辑
function enhanceOption(option, chart) {
  const enhanced = JSON.parse(JSON.stringify(option))
  enhanced.toolbox = {
    show: true,
    right: 10,
    top: 5,
    iconStyle: { borderColor: '#999' },
    emphasis: { iconStyle: { borderColor: '#00ff41' } },
    feature: {
      dataZoom: { yAxisIndex: 'none', title: { zoom: '框选缩放', back: '还原缩放' } },
      restore: { title: '还原' },
      saveAsImage: { pixelRatio: 2, title: '保存图片' }
    }
  }
  if (hasYAxis(chart)) {
    if (!enhanced.dataZoom) enhanced.dataZoom = []
    enhanced.dataZoom.push({
      type: 'slider',
      yAxisIndex: 0,
      filterMode: 'none',
      right: 0,
      width: 20,
      borderColor: '#333',
      fillerColor: 'rgba(0, 255, 65, 0.15)',
      handleStyle: { color: '#00ff41', borderColor: '#00ff41' },
      textStyle: { color: '#999' }
    })
  }
  return enhanced
}

// 核心渲染：销毁旧实例与旧 resize 监听，逐个初始化 ECharts 实例并 setOption，注册 resize
// AI-assisted: 使用 Claude 实现 ECharts 实例初始化与销毁，手动调整了 resize 监听注册/清理逻辑
function renderCharts() {
  resizeHandlers.value.forEach(h => window.removeEventListener('resize', h))
  resizeHandlers.value = []
  chartInstances.value.forEach(inst => { if (inst) inst.dispose() })
  chartInstances.value = []

  allCharts.value.forEach((item, index) => {
    const container = chartRefs.value[index]
    if (!container) return

    if (!panelStates[index]) {
      panelStates[index] = {
        open: false,
        yMin: '',
        yMax: '',
        xInterval: '',
        chartType: item.chart.chart_type,
        showLabels: false,
        smooth: false,
        colorTheme: 'classic'
      }
    }

    const instance = echarts.init(container, null, { renderer: 'canvas' })
    const mergedOption = mergeDarkOption(item.chart.option || {})
    const enhancedOption = enhanceOption(mergedOption, item.chart)
    instance.setOption(enhancedOption, true)
    chartInstances.value[index] = instance

    const resizeHandler = () => instance.resize()
    window.addEventListener('resize', resizeHandler)
    resizeHandlers.value.push(resizeHandler)
  })
}

// ---- 固定/取消固定图表 ----

// 取消固定图表：从 pinnedCharts 移除后重新渲染
// AI-assisted: 使用 Claude 实现取消固定逻辑，人工校验后保留原逻辑
function unpinChart(index) {
  const currentCount = store.charts.length
  const pinnedIndex = index - currentCount
  if (pinnedIndex >= 0) {
    store.pinnedCharts.splice(pinnedIndex, 1)
    nextTick(() => renderCharts())
  }
}

// ---- 控制面板操作 ----

// 切换设置面板的展开/收起状态
// AI-assisted: 使用 Claude 实现面板折叠切换，未做大幅修改
function togglePanel(index) {
  if (panelStates[index]) panelStates[index].open = !panelStates[index].open
}

// 更新指定图表面板的某个状态字段（受控输入）
// AI-assisted: 使用 Claude 实现面板状态更新，未做大幅修改
function updatePanelState(index, key, value) {
  if (!panelStates[index]) return
  panelStates[index][key] = value
}

// 读取图表指定坐标轴（x/y）当前名称，用于回显输入框
// AI-assisted: 使用 Claude 实现坐标轴名称读取，未做大幅修改
function getAxisName(chart, axis) {
  if (!chart?.option) return ''
  const ax = chart.option[axis === 'x' ? 'xAxis' : 'yAxis']
  if (!ax) return ''
  return ax.name || ''
}

// 应用 X/Y 轴标签到图表实例并写回原始 option
// AI-assisted: 使用 Claude 实现坐标轴名称应用，人工校验后保留原逻辑
function applyAxisNames(index) {
  const instance = chartInstances.value[index]
  const item = allCharts.value[index]
  if (!instance || !item) return

  const state = panelStates[index]
  const option = {}

  if (state.xAxisName !== undefined) {
    option.xAxis = { name: state.xAxisName, nameLocation: 'middle', nameGap: 30 }
    if (item.chart.option?.xAxis) {
      item.chart.option.xAxis.name = state.xAxisName
    }
  }
  if (state.yAxisName !== undefined) {
    option.yAxis = { name: state.yAxisName, nameLocation: 'end' }
    if (item.chart.option?.yAxis) {
      item.chart.option.yAxis.name = state.yAxisName
    }
  }

  instance.setOption(option)
}

// 应用 Y 轴最小/最大范围到图表实例
// AI-assisted: 使用 Claude 实现 Y 轴范围应用，未做大幅修改
function applyYAxis(index) {
  const instance = chartInstances.value[index]
  if (!instance) return
  const state = panelStates[index]
  const option = { yAxis: {} }
  if (state.yMin !== '' && state.yMin !== null) option.yAxis.min = Number(state.yMin)
  if (state.yMax !== '' && state.yMax !== null) option.yAxis.max = Number(state.yMax)
  instance.setOption(option)
}

// 重置 Y 轴范围，清除面板输入与实例上的 min/max
// AI-assisted: 使用 Claude 实现 Y 轴范围重置，未做大幅修改
function resetYAxis(index) {
  const instance = chartInstances.value[index]
  if (!instance) return
  panelStates[index].yMin = ''
  panelStates[index].yMax = ''
  instance.setOption({ yAxis: { min: undefined, max: undefined } }, false)
}

// 应用 X 轴刻度间距，校验非法值后写入实例
// AI-assisted: 使用 Claude 实现 X 轴间距应用与校验，未做大幅修改
function applyXInterval(index) {
  const instance = chartInstances.value[index]
  if (!instance) return
  const val = panelStates[index].xInterval
  if (val === '' || val === null) return
  const interval = Number(val)
  if (isNaN(interval) || interval < 0) return
  instance.setOption({ xAxis: { interval } })
}

// 重置 X 轴刻度间距为自动
// AI-assisted: 使用 Claude 实现 X 轴间距重置，未做大幅修改
function resetXInterval(index) {
  const instance = chartInstances.value[index]
  if (!instance) return
  panelStates[index].xInterval = ''
  instance.setOption({ xAxis: { interval: undefined } }, false)
}

// 切换图表类型：更新状态并通过后端重新生成数据，期间显示加载遮罩
// AI-assisted: 使用 Claude 生成图表类型切换主流程，人工校验后保留原逻辑
async function switchType(index, newType) {
  const item = allCharts.value[index]
  const instance = chartInstances.value[index]
  if (!item || !instance) return

  panelStates[index].chartType = newType

  // 统一走后端，保证数据结构正确
  loadingIndex.value = index
  try {
    await switchTypeBackend(index, newType)
  } finally {
    loadingIndex.value = -1
  }
}

// 调用后端 rechart 接口以新类型重新生成图表，并用新 option 重建对应 ECharts 实例
// AI-assisted: 使用 Claude 实现后端切换图表类型与实例重建，手动调整了错误日志与定位逻辑
async function switchTypeBackend(index, newType) {
  if (!store.sessionId) return
  const userMessages = store.messages.filter(m => m.role === 'user')
  const lastQuery = userMessages[userMessages.length - 1]?.content
  if (!lastQuery) return

  try {
    const result = await rechartAPI(store.sessionId, lastQuery, newType)
    if (result.success && result.charts && result.charts.length > 0) {
      const newChart = result.charts[0]
      const currentCount = store.charts.length
      if (index < currentCount) {
        store.charts[index] = newChart
      } else {
        store.pinnedCharts[index - currentCount] = newChart
      }
      await nextTick()
      const container = chartRefs.value[index]
      if (container) {
        if (chartInstances.value[index]) chartInstances.value[index].dispose()
        const instance = echarts.init(container, null, { renderer: 'canvas' })
        const mergedOption = mergeDarkOption(newChart.option || {})
        const enhancedOption = enhanceOption(mergedOption, newChart)
        instance.setOption(enhancedOption, true)
        chartInstances.value[index] = instance
      }
    }
  } catch (e) {
    console.error('图表类型切换失败:', e)
  }
}

// 切换数据标签显示，遍历所有 series 设置 label.show
// AI-assisted: 使用 Claude 实现数据标签开关，未做大幅修改
function toggleLabels(index) {
  const instance = chartInstances.value[index]
  if (!instance) return
  panelStates[index].showLabels = !panelStates[index].showLabels
  const show = panelStates[index].showLabels
  const currentOption = instance.getOption()
  const series = currentOption.series
  if (!series) return
  instance.setOption({
    series: series.map(s => ({ ...s, label: { ...(s.label || {}), show } }))
  })
}

// 切换折线平滑曲线，遍历所有 series 设置 smooth
// AI-assisted: 使用 Claude 实现平滑曲线开关，未做大幅修改
function toggleSmooth(index) {
  const instance = chartInstances.value[index]
  if (!instance) return
  panelStates[index].smooth = !panelStates[index].smooth
  const smooth = panelStates[index].smooth
  const currentOption = instance.getOption()
  const series = currentOption.series
  if (!series) return
  instance.setOption({ series: series.map(s => ({ ...s, smooth })) })
}

// 切换配色方案：饼图按数据项着色，其余按 series 着色
// AI-assisted: 使用 Claude 实现配色方案切换，手动调整了饼图与普通图的着色分支
function switchColorTheme(index, themeName) {
  const instance = chartInstances.value[index]
  const item = allCharts.value[index]
  if (!instance || !item) return

  panelStates[index].colorTheme = themeName
  const colors = COLOR_THEMES[themeName]
  const currentOption = instance.getOption()
  const chartType = item.chart.chart_type

  if (chartType === 'pie') {
    const series = currentOption.series
    if (series && series[0] && series[0].data) {
      instance.setOption({
        series: [{
          ...series[0],
          data: series[0].data.map((d, i) => ({
            ...d,
            itemStyle: { ...(d.itemStyle || {}), color: colors[i % colors.length] }
          }))
        }]
      })
    }
  } else {
    const series = currentOption.series
    if (series) {
      instance.setOption({
        series: series.map((s, i) => ({
          ...s,
          itemStyle: { ...(s.itemStyle || {}), color: colors[i % colors.length] }
        }))
      })
    }
  }
}

// 标题编辑失焦：将新标题写入 ECharts 实例与原始 option
// AI-assisted: 使用 Claude 实现可编辑标题保存，未做大幅修改
function handleTitleBlur(index, event) {
  const instance = chartInstances.value[index]
  if (!instance) return
  const newTitle = event.target.innerText.trim()
  if (!newTitle) return
  instance.setOption({ title: { text: newTitle } })
  const item = allCharts.value[index]
  if (item.chart.option) {
    if (!item.chart.option.title) item.chart.option.title = {}
    item.chart.option.title.text = newTitle
  }
}

// 关闭图表区：仅隐藏可见性标志，不销毁组件、不清空数据
// AI-assisted: 使用 Claude 实现图表区关闭逻辑，未做大幅修改
function handleCloseCharts() {
  // 只隐藏图表区域，不销毁组件，不清空数据
  store.chartsVisible = false
  store.viewingHistoryCharts = false
  store.viewingMessageIndex = -1
}

watch(() => [store.charts, store.pinnedCharts], async () => {
  if (skipNextWatch) {
    skipNextWatch = false
    return
  }
  // 不可见时跳过渲染
  if (!store.chartsVisible) return
  Object.keys(panelStates).forEach(k => delete panelStates[k])
  await nextTick()
  tryRenderCharts()
}, { deep: true })

// 尝试渲染图表（带重试机制，确保 DOM 容器已就绪）
// AI-assisted: 使用 Claude 实现带重试的渲染调度，手动调整了重试次数与延迟参数
function tryRenderCharts(retries = 0) {
  const hasCharts = allCharts.value.length > 0
  const hasContainers = allCharts.value.every((_, index) => !!chartRefs.value[index])

  if (hasCharts && hasContainers) {
    renderCharts()
  } else if (hasCharts && retries < 5) {
    // DOM 容器尚未就绪，短暂延迟后重试
    setTimeout(() => tryRenderCharts(retries + 1), 50)
  }
}

onMounted(() => {
  if (allCharts.value.length > 0) {
    nextTick(() => tryRenderCharts())
  }
})

onUnmounted(() => {
  resizeHandlers.value.forEach(h => window.removeEventListener('resize', h))
  resizeHandlers.value = []
  chartInstances.value.forEach(inst => { if (inst) inst.dispose() })
  chartInstances.value = []
  document.removeEventListener('mousemove', onFreeDragMove)
  document.removeEventListener('mouseup', onFreeDragEnd)
})
</script>

<style scoped>
.chart-viewer {
  background: var(--theme-dark);
  border: 1px solid var(--theme-border);
  border-radius: var(--theme-radius);
  padding: 1rem;
}

.chart-title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.chart-title {
  margin: 0;
  font-size: 0.85rem;
  color: var(--theme-white-dim);
  text-transform: uppercase;
  letter-spacing: 0.15em;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.title-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--theme-green);
}

.btn-close-charts {
  width: 28px;
  height: 28px;
  border: 1px solid var(--theme-border);
  background: transparent;
  color: var(--theme-white-dim);
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.btn-close-charts:hover {
  border-color: var(--theme-red);
  color: var(--theme-red);
  background: rgba(255, 68, 68, 0.08);
}

.btn-action {
  width: 28px;
  height: 28px;
  border: 1px solid var(--theme-border);
  background: transparent;
  color: var(--theme-white-dim);
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.btn-action:hover {
  border-color: var(--theme-green);
  color: var(--theme-green);
  background: var(--theme-green-dim);
}

.charts-container {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
  gap: 1rem;
}

.chart-item {
  background: var(--theme-dark-2);
  border: 1px solid var(--theme-border);
  border-radius: var(--theme-radius-sm);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  transition: transform 0.15s, box-shadow 0.15s;
  position: relative;
}

.chart-item.chart-pinned {
  border-left: 2px solid #ffd93d;
}

/* ---- 图表标题栏 ---- */
.chart-header {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid var(--theme-border);
  background: rgba(0, 0, 0, 0.2);
}

.chart-label {
  font-size: 0.85rem;
  color: var(--theme-white);
  font-weight: 500;
  outline: none;
  cursor: text;
  border-bottom: 1px dashed transparent;
  transition: border-color 0.2s;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chart-label:hover { border-bottom-color: var(--theme-border); }
.chart-label:focus { border-bottom-color: var(--theme-green); }

.chart-label.pinned-label::after {
  content: ' (固定)';
  color: #ffd93d;
  font-size: 0.75rem;
  font-weight: 400;
}

.chart-header-btns {
  display: flex;
  gap: 0.25rem;
  flex-shrink: 0;
}

.header-btn {
  width: 24px;
  height: 24px;
  border: 1px solid var(--theme-border);
  background: transparent;
  color: var(--theme-red);
  border-radius: 3px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.header-btn:hover {
  background: var(--theme-red);
  color: var(--theme-black);
  border-color: var(--theme-red);
}

.settings-toggle {
  width: 24px;
  height: 24px;
  border: 1px solid var(--theme-border);
  background: transparent;
  color: var(--theme-white-dim);
  border-radius: 3px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.settings-toggle:hover,
.settings-toggle.active {
  border-color: var(--theme-green);
  color: var(--theme-green);
  background: var(--theme-green-dim);
}

/* ---- 设置面板 ---- */
.settings-panel {
  max-height: 0;
  overflow: hidden;
  transition: max-height 0.3s ease, padding 0.3s ease;
  background: rgba(0, 0, 0, 0.3);
  border-bottom: 1px solid transparent;
}

.settings-panel.open {
  max-height: 300px;
  padding: 0.6rem 0.75rem;
  border-bottom-color: var(--theme-border);
}

.setting-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.4rem;
}

.setting-row:last-child { margin-bottom: 0; }

.setting-label {
  font-size: 0.75rem;
  color: var(--theme-white-dim);
  width: 56px;
  flex-shrink: 0;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.setting-inputs {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  flex: 1;
}

.setting-input {
  width: 70px;
  padding: 0.25rem 0.4rem;
  background: var(--theme-dark);
  border: 1px solid var(--theme-border);
  border-radius: 3px;
  color: var(--theme-white);
  font-size: 0.8rem;
  outline: none;
  transition: border-color 0.2s;
}

.setting-input:focus { border-color: var(--theme-green); }
.setting-input::placeholder { color: #555; }

.axis-name-input { width: 90px; }

.setting-sep { color: var(--theme-white-dim); font-size: 0.8rem; }

.btn-sm {
  padding: 0.2rem 0.6rem;
  background: var(--theme-green);
  color: var(--theme-black);
  border: none;
  border-radius: 3px;
  font-size: 0.75rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-sm:hover { box-shadow: 0 0 8px rgba(0, 255, 65, 0.3); }

.btn-secondary {
  background: transparent;
  color: var(--theme-white-dim);
  border: 1px solid var(--theme-border);
}

.btn-secondary:hover {
  border-color: var(--theme-green);
  color: var(--theme-green);
  box-shadow: none;
}

.setting-btns {
  display: flex;
  gap: 0.3rem;
  flex-wrap: wrap;
  flex: 1;
}

.btn-type {
  padding: 0.2rem 0.55rem;
  background: transparent;
  border: 1px solid var(--theme-border);
  border-radius: 3px;
  font-size: 0.75rem;
  color: var(--theme-white-dim);
  cursor: pointer;
  transition: all 0.2s;
}

.btn-type:hover { border-color: var(--theme-green); color: var(--theme-green); }

.btn-type.active {
  background: var(--theme-green);
  color: var(--theme-black);
  border-color: var(--theme-green);
  font-weight: 500;
}

.setting-toggles { display: flex; gap: 1rem; flex: 1; }

.toggle-label {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.8rem;
  color: var(--theme-white-dim);
  cursor: pointer;
  user-select: none;
}

.toggle-label input[type="checkbox"] {
  width: 14px;
  height: 14px;
  accent-color: var(--theme-green);
  cursor: pointer;
}

.btn-theme {
  display: flex;
  gap: 2px;
  padding: 0.25rem 0.4rem;
  background: transparent;
  border: 1px solid var(--theme-border);
  border-radius: 3px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-theme:hover { border-color: var(--theme-green); }
.btn-theme.active { border-color: var(--theme-green); background: var(--theme-green-dim); }

.color-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.echarts-chart {
  width: 100%;
  min-height: 250px;
}

/* ---- 加载遮罩 ---- */
.chart-loading {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  z-index: 10;
  border-radius: var(--theme-radius-sm);
}

.loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--theme-border);
  border-top-color: var(--theme-green);
  border-radius: 50%;
  animation: chart-spin 0.8s linear infinite;
}

@keyframes chart-spin {
  to { transform: rotate(360deg); }
}

.loading-text {
  font-size: 0.8rem;
  color: var(--theme-green);
  letter-spacing: 0.1em;
}

@media (max-width: 768px) {
  .charts-container { grid-template-columns: 1fr; }
}
</style>
