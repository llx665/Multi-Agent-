const ADMIN_NAV = [
  {
    key: 'dashboard',
    label: '总览',
    description: '查看后台入口与运行概况',
    to: '/dashboard',
    roles: ['operator', 'admin', 'super_admin']
  },
  {
    key: 'memory',
    label: '记忆管理',
    description: '管理三层记忆与偏好修正',
    to: '/memory',
    roles: ['operator', 'admin', 'super_admin']
  },
  {
    key: 'knowledge',
    label: '知识库管理',
    description: '维护知识文件可见性与发布状态',
    to: '/knowledge',
    roles: ['operator', 'admin', 'super_admin']
  },
  {
    key: 'settings',
    label: '系统设置',
    description: '查看系统参数与权限策略',
    to: '/settings',
    roles: ['admin', 'super_admin']
  },
  {
    key: 'users',
    label: '账号管理',
    description: '管理角色、状态与账号权限',
    to: '/users',
    roles: ['admin', 'super_admin']
  }
]

export function buildAdminNav(role = '') {
  return ADMIN_NAV.filter((item) => item.roles.includes(role))
}

export function resolveAdminHome(role = '') {
  return buildAdminNav(role)[0]?.to || '/dashboard'
}
