import { createRouter, createWebHashHistory } from 'vue-router'

import { getAuthUser } from '../auth/session.js'
import MemoryAdminPage from './pages/MemoryAdminPage.vue'
import DashboardPage from './pages/DashboardPage.vue'
import KnowledgeAdminPage from './pages/KnowledgeAdminPage.vue'
import SettingsAdminPage from './pages/SettingsAdminPage.vue'
import UsersAdminPage from './pages/UsersAdminPage.vue'
import { resolveAdminHome } from './nav.js'

const routes = [
  {
    path: '/',
    redirect: () => resolveAdminHome(getAuthUser()?.role)
  },
  {
    path: '/dashboard',
    component: DashboardPage,
    meta: {
      title: '后台总览',
      description: '统一查看后台模块与可用能力。',
      roles: ['operator', 'admin', 'super_admin']
    }
  },
  {
    path: '/memory',
    component: MemoryAdminPage,
    meta: {
      title: '记忆管理',
      description: '搜索用户、修正偏好并清理记忆快照。',
      roles: ['operator', 'admin', 'super_admin']
    }
  },
  {
    path: '/knowledge',
    component: KnowledgeAdminPage,
    meta: {
      title: '知识库管理',
      description: '控制文件对前台的显示、隐藏与发布状态。',
      roles: ['operator', 'admin', 'super_admin']
    }
  },
  {
    path: '/settings',
    component: SettingsAdminPage,
    meta: {
      title: '系统设置',
      description: '查看系统参数、偏好策略与权限模型。',
      roles: ['admin', 'super_admin']
    }
  },
  {
    path: '/users',
    component: UsersAdminPage,
    meta: {
      title: '账号管理',
      description: '统一维护账号角色和后台访问权限。',
      roles: ['admin', 'super_admin']
    }
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

router.beforeEach((to) => {
  const role = getAuthUser()?.role
  if (!role) {
    return true
  }

  const allowedRoles = to.meta?.roles || []
  if (allowedRoles.length > 0 && !allowedRoles.includes(role)) {
    return resolveAdminHome(role)
  }

  return true
})

export default router
