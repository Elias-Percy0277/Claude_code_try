<template>
  <div class="file-upload">
    <div class="upload-area" :class="{ 'dragover': isDragover }" @dragover.prevent="dragover = true" @dragleave.prevent="dragover = false" @drop.prevent="handleDrop" @click="selectFile">
      <input ref="fileInput" type="file" accept=".csv,.xlsx,.json,.xls,.data,.test,.names,.index" multiple @change="handleFileChange" hidden>
      <div class="upload-icon">
        <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
          <path d="M24 6L24 30" stroke="var(--theme-green)" stroke-width="2" stroke-linecap="round"/>
          <path d="M16 14L24 6L32 14" stroke="var(--theme-green)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M6 30L6 38C6 40.2091 7.79086 42 10 42L38 42C40.2091 42 42 40.2091 42 38L42 30" stroke="var(--theme-green)" stroke-width="2" stroke-linecap="round"/>
        </svg>
      </div>
      <p class="upload-text">点击或拖拽文件到此处</p>
      <p class="upload-hint">CSV / Excel / JSON / DATA / TEST / NAMES / INDEX</p>
      <p class="upload-hint">可多选，最大 60MB</p>
    </div>

    <!-- 已选文件列表 -->
    <div v-if="selectedFiles.length > 0" class="selected-files">
      <div class="files-header">
        <span>已选择 {{ selectedFiles.length }} 个文件</span>
        <button @click.stop="clearFiles" class="btn-clear">清空</button>
      </div>
      <div class="file-list">
        <div v-for="(file, index) in selectedFiles" :key="index" class="file-item">
          <span class="file-icon">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <rect x="2" y="1" width="12" height="14" rx="1.5" stroke="var(--theme-green)" stroke-width="1.2"/>
              <path d="M5 5H11M5 8H11M5 11H8" stroke="var(--theme-green)" stroke-width="1" stroke-linecap="round"/>
            </svg>
          </span>
          <span class="file-name">{{ file.name }}</span>
          <span class="file-size">{{ formatSize(file.size) }}</span>
          <button @click.stop="removeFile(index)" class="btn-remove">×</button>
        </div>
      </div>
      <button @click.stop="handleUpload" class="btn-upload" :disabled="isUploading">
        {{ isUploading ? '上传中...' : `上传 ${selectedFiles.length} 个文件` }}
      </button>
    </div>

    <!-- 上传进度 -->
    <div v-if="isUploading" class="upload-progress">
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: uploadProgress + '%' }"></div>
      </div>
      <p class="progress-text">上传中... {{ uploadProgress }}%</p>
    </div>

    <!-- 错误提示 -->
    <div v-if="error" class="upload-error">
      {{ error }}
      <button @click="error = null" class="btn-close-error">×</button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { uploadFiles } from '@/api/client'

const emit = defineEmits(['uploaded'])

const fileInput = ref(null)
const dragover = ref(false)
const isUploading = ref(false)
const uploadProgress = ref(0)
const error = ref(null)
const selectedFiles = ref([])

const isDragover = dragover

function selectFile() {
  fileInput.value.click()
}

function handleFileChange(e) {
  const files = Array.from(e.target.files)
  addFiles(files)
  e.target.value = ''
}

function handleDrop(e) {
  dragover.value = false
  const files = Array.from(e.dataTransfer.files)
  addFiles(files)
}

function addFiles(files) {
  const allowedExtensions = ['.csv', '.xlsx', '.json', '.xls', '.data', '.test', '.names', '.index']
  const maxSize = 60 * 1024 * 1024

  for (const file of files) {
    const ext = '.' + file.name.split('.').pop().toLowerCase()

    if (!allowedExtensions.includes(ext)) {
      error.value = `不支持的文件格式: ${ext} (${file.name})`
      return
    }

    if (file.size > maxSize) {
      error.value = `文件过大 (${file.name}: ${(file.size / 1024 / 1024).toFixed(1)}MB)`
      return
    }

    if (!selectedFiles.value.some(f => f.name === file.name && f.size === file.size)) {
      selectedFiles.value.push(file)
    }
  }

  error.value = null
}

function removeFile(index) {
  selectedFiles.value.splice(index, 1)
}

function clearFiles() {
  selectedFiles.value = []
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}

async function handleUpload() {
  if (selectedFiles.value.length === 0) return

  error.value = null
  isUploading.value = true
  uploadProgress.value = 0

  try {
    const progressInterval = setInterval(() => {
      if (uploadProgress.value < 90) {
        uploadProgress.value += 10
      }
    }, 200)

    const result = await uploadFiles(selectedFiles.value)

    clearInterval(progressInterval)
    uploadProgress.value = 100

    emit('uploaded', result)

    setTimeout(() => {
      isUploading.value = false
      uploadProgress.value = 0
      selectedFiles.value = []
    }, 500)
  } catch (err) {
    error.value = err.message || '上传失败，请重试'
    isUploading.value = false
    uploadProgress.value = 0
  }
}
</script>

<style scoped>
.file-upload {
  background: var(--theme-dark);
  border: 1px solid var(--theme-border);
  border-radius: var(--theme-radius);
  padding: 1.5rem;
}

.upload-area {
  border: 1px dashed var(--theme-border);
  border-radius: var(--theme-radius);
  padding: 3rem 1.5rem;
  text-align: center;
  cursor: pointer;
  transition: var(--theme-transition);
  position: relative;
}

.upload-area::before {
  content: '';
  position: absolute;
  inset: -1px;
  border-radius: var(--theme-radius);
  background: linear-gradient(135deg, transparent, rgba(23, 247, 0, 0.1), transparent);
  opacity: 0;
  transition: opacity 0.3s ease;
  pointer-events: none;
}

.upload-area:hover {
  border-color: var(--theme-green);
}

.upload-area:hover::before {
  opacity: 1;
}

.upload-area.dragover {
  border-color: var(--theme-green);
  background: var(--theme-green-dim);
  box-shadow: 0 0 30px rgba(23, 247, 0, 0.15);
}

.upload-icon {
  margin-bottom: 1rem;
}

.upload-text {
  margin: 0 0 0.5rem 0;
  font-size: 1.1rem;
  color: var(--theme-white);
  font-weight: 500;
}

.upload-hint {
  margin: 0.25rem 0 0 0;
  font-size: 0.8rem;
  color: var(--theme-white-dim);
  letter-spacing: 0.05em;
}

.selected-files {
  margin-top: 1rem;
  border: 1px solid var(--theme-border);
  border-radius: var(--theme-radius-sm);
  overflow: hidden;
}

.files-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 1rem;
  background: var(--theme-dark-2);
  border-bottom: 1px solid var(--theme-border);
  font-size: 0.85rem;
  color: var(--theme-white-dim);
}

.btn-clear {
  padding: 0.25rem 0.75rem;
  border: 1px solid var(--theme-border);
  background: transparent;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.85rem;
  color: var(--theme-white-dim);
  transition: var(--theme-transition);
}

.btn-clear:hover {
  border-color: var(--theme-green);
  color: var(--theme-green);
}

.file-list {
  max-height: 200px;
  overflow-y: auto;
}

.file-item {
  display: flex;
  align-items: center;
  padding: 0.6rem 1rem;
  border-bottom: 1px solid var(--theme-border);
  gap: 0.5rem;
}

.file-item:last-child {
  border-bottom: none;
}

.file-icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
}

.file-name {
  flex: 1;
  font-size: 0.9rem;
  color: var(--theme-white);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-size {
  font-size: 0.8rem;
  color: var(--theme-white-dim);
  flex-shrink: 0;
}

.btn-remove {
  width: 24px;
  height: 24px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--theme-red);
  border-radius: 4px;
  cursor: pointer;
  font-size: 1.2rem;
  line-height: 1;
  flex-shrink: 0;
  transition: var(--theme-transition);
}

.btn-remove:hover {
  border-color: var(--theme-red);
  background: rgba(255, 68, 68, 0.1);
}

.btn-upload {
  width: 100%;
  padding: 0.75rem;
  border: none;
  background: var(--theme-green);
  color: var(--theme-black);
  font-weight: 600;
  letter-spacing: 0.05em;
  cursor: pointer;
  font-size: 0.95rem;
  transition: var(--theme-transition);
}

.btn-upload:hover:not(:disabled) {
  box-shadow: 0 0 25px rgba(23, 247, 0, 0.4);
}

.btn-upload:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  box-shadow: none;
}

.upload-progress {
  margin-top: 1rem;
}

.progress-bar {
  height: 3px;
  background: var(--theme-dark-2);
  border-radius: 2px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--theme-green), #4dff1a);
  transition: width 0.3s;
  box-shadow: 0 0 10px rgba(23, 247, 0, 0.5);
}

.progress-text {
  margin: 0.5rem 0 0 0;
  font-size: 0.85rem;
  color: var(--theme-white-dim);
  text-align: center;
}

.upload-error {
  margin-top: 1rem;
  padding: 0.75rem;
  background: rgba(255, 68, 68, 0.1);
  border: 1px solid rgba(255, 68, 68, 0.3);
  border-left: 3px solid var(--theme-red);
  border-radius: 4px;
  color: var(--theme-red);
  font-size: 0.9rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.btn-close-error {
  background: none;
  border: none;
  color: var(--theme-red);
  font-size: 1.2rem;
  cursor: pointer;
  padding: 0;
  width: 20px;
  height: 20px;
  line-height: 1;
  opacity: 0.7;
  transition: opacity 0.2s;
}

.btn-close-error:hover {
  opacity: 1;
}
</style>
