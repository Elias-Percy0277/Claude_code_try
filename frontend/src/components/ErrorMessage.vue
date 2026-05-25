<template>
  <div class="error-message">
    <div class="error-icon">
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
        <circle cx="10" cy="10" r="8" stroke="var(--theme-red)" stroke-width="1.5"/>
        <path d="M10 6V11" stroke="var(--theme-red)" stroke-width="1.5" stroke-linecap="round"/>
        <circle cx="10" cy="14" r="1" fill="var(--theme-red)"/>
      </svg>
    </div>
    <div class="error-content">
      <p class="error-text">{{ message }}</p>
    </div>
    <button @click="$emit('close')" class="error-close">
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
        <path d="M2 2L12 12M12 2L2 12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
      </svg>
    </button>
  </div>
</template>

<script setup>
defineProps({
  message: {
    type: String,
    required: true
  }
})

defineEmits(['close'])
</script>

<style scoped>
.error-message {
  background: rgba(255, 68, 68, 0.08);
  border: 1px solid rgba(255, 68, 68, 0.25);
  border-left: 2px solid var(--theme-red);
  border-radius: var(--theme-radius-sm);
  padding: 1rem;
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.error-icon {
  flex-shrink: 0;
}

.error-content {
  flex: 1;
  min-width: 0;
}

.error-text {
  margin: 0;
  color: var(--theme-red);
  font-size: 0.9rem;
}

.error-close {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--theme-white-dim);
  padding: 0.25rem;
  flex-shrink: 0;
  transition: color 0.2s;
  display: flex;
  align-items: center;
}

.error-close:hover {
  color: var(--theme-red);
}
</style>
