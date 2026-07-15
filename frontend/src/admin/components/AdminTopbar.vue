<template>
  <header class="admin-topbar">
    <div>
      <p class="eyebrow">{{ route.meta.title || '后台工作台' }}</p>
      <h2>{{ route.meta.title || '后台工作台' }}</h2>
      <p class="summary">{{ route.meta.description || '统一管理系统的后台入口。' }}</p>
    </div>

    <div class="topbar-actions">
      <div class="identity-chip">
        <span>{{ currentUser.username }}</span>
        <strong>{{ roleLabel }}</strong>
      </div>
      <button class="ghost-btn" @click="$emit('sign-out')">退出</button>
    </div>
  </header>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const props = defineProps({
  currentUser: {
    type: Object,
    required: true
  }
})

defineEmits(['sign-out'])

const route = useRoute()
const roleLabel = computed(() => {
  const labels = {
    operator: '运营员',
    admin: '管理员',
    super_admin: '超级管理员'
  }
  return labels[props.currentUser?.role] || '普通用户'
})
</script>

<style scoped>
.admin-topbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding: 20px 24px;
  background: rgba(255, 252, 247, 0.78);
  backdrop-filter: blur(18px);
  border: 1px solid rgba(33, 44, 66, 0.08);
  border-radius: 26px;
  box-shadow: 0 16px 40px rgba(33, 44, 66, 0.08);
}

.eyebrow {
  font-size: 11px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--text-muted);
}

h2 {
  margin-top: 10px;
  font-family: Georgia, 'Times New Roman', serif;
  font-size: clamp(28px, 3.4vw, 38px);
}

.summary {
  margin-top: 10px;
  max-width: 620px;
  color: var(--text-secondary);
  line-height: 1.7;
}

.topbar-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.identity-chip {
  min-width: 168px;
  padding: 12px 16px;
  border-radius: 18px;
  background: rgba(16, 98, 89, 0.08);
  border: 1px solid rgba(16, 98, 89, 0.12);
}

.identity-chip span,
.identity-chip strong {
  display: block;
}

.identity-chip span {
  color: var(--text-secondary);
  font-size: 13px;
}

.identity-chip strong {
  margin-top: 4px;
}

.ghost-btn {
  padding: 12px 16px;
  border-radius: 999px;
  border: 1px solid rgba(16, 98, 89, 0.16);
  background: rgba(255, 255, 255, 0.82);
  font-weight: 600;
}

@media (max-width: 880px) {
  .admin-topbar {
    flex-direction: column;
    align-items: flex-start;
  }

  .topbar-actions {
    width: 100%;
    justify-content: space-between;
  }
}
</style>
