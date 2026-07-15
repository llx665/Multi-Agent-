<template>
  <div class="admin-frame">
    <AdminSidebar :items="navItems" :current-user="currentUser" />

    <div class="admin-main">
      <AdminTopbar :current-user="currentUser" @sign-out="$emit('sign-out')" />
      <main class="admin-content">
        <slot />
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

import AdminSidebar from '../components/AdminSidebar.vue'
import AdminTopbar from '../components/AdminTopbar.vue'
import { buildAdminNav } from '../nav.js'

const props = defineProps({
  currentUser: {
    type: Object,
    required: true
  }
})

defineEmits(['sign-out'])

const navItems = computed(() => buildAdminNav(props.currentUser?.role))
</script>

<style scoped>
.admin-frame {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  background:
    radial-gradient(circle at 0% 0%, rgba(12, 113, 102, 0.16), transparent 26%),
    radial-gradient(circle at 100% 20%, rgba(196, 111, 36, 0.12), transparent 26%),
    linear-gradient(135deg, #efe6d8 0%, #f9f4ec 38%, #f2f8f7 100%);
}

.admin-main {
  min-width: 0;
  padding: 20px 20px 24px 0;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.admin-content {
  min-height: 0;
}

@media (max-width: 1080px) {
  .admin-frame {
    grid-template-columns: 1fr;
  }

  .admin-main {
    padding: 0 16px 24px;
  }
}
</style>
