<template>
  <aside class="admin-sidebar">
    <div class="brand-card">
      <p class="brand-kicker">Backoffice</p>
      <h1>运营控制台</h1>
      <p>把记忆、知识库、设置和账号管理收敛到同一套后台工作流。</p>
    </div>

    <div class="role-card">
      <span class="role-label">当前角色</span>
      <strong>{{ roleLabel }}</strong>
      <small>{{ currentUser.username }}</small>
    </div>

    <nav class="nav-list" aria-label="后台导航">
      <RouterLink
        v-for="item in items"
        :key="item.key"
        :to="item.to"
        class="nav-item"
        active-class="active"
      >
        <span class="nav-title">{{ item.label }}</span>
        <span class="nav-copy">{{ item.description }}</span>
      </RouterLink>
    </nav>
  </aside>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  items: {
    type: Array,
    default: () => []
  },
  currentUser: {
    type: Object,
    required: true
  }
})

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
.admin-sidebar {
  padding: 24px 18px;
  display: flex;
  flex-direction: column;
  gap: 18px;
  color: #f7f3ee;
  background: linear-gradient(180deg, #17363a 0%, #0f232d 100%);
  border-right: 1px solid rgba(255, 255, 255, 0.08);
}

.brand-card,
.role-card {
  border-radius: 24px;
  padding: 20px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0.03));
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.brand-kicker,
.role-label {
  font-size: 11px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: rgba(247, 243, 238, 0.58);
}

h1 {
  margin-top: 10px;
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 34px;
  line-height: 1.05;
}

p,
small {
  margin-top: 10px;
  color: rgba(247, 243, 238, 0.74);
  line-height: 1.65;
}

strong {
  display: block;
  margin-top: 8px;
  font-size: 18px;
}

.nav-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.nav-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 16px 18px;
  border-radius: 18px;
  text-decoration: none;
  color: inherit;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.03);
  transition: transform var(--transition), background var(--transition), border-color var(--transition);
}

.nav-item:hover {
  transform: translateY(-1px);
  background: rgba(255, 255, 255, 0.08);
}

.nav-item.active {
  background: linear-gradient(135deg, rgba(240, 188, 120, 0.18), rgba(18, 150, 135, 0.22));
  border-color: rgba(240, 188, 120, 0.28);
}

.nav-title {
  font-size: 15px;
  font-weight: 700;
}

.nav-copy {
  font-size: 12px;
  line-height: 1.6;
  color: rgba(247, 243, 238, 0.66);
}

@media (max-width: 1080px) {
  .admin-sidebar {
    border-right: none;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }
}
</style>
