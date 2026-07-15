import { describe, expect, it } from 'vitest'

import { buildAdminNav, resolveAdminHome } from '../nav'

describe('buildAdminNav', () => {
  it('hides user management for operator', () => {
    const items = buildAdminNav('operator')
    expect(items.some((item) => item.key === 'users')).toBe(false)
    expect(items.map((item) => item.key)).toEqual(['dashboard', 'memory', 'knowledge'])
  })

  it('shows all modules for super_admin', () => {
    const items = buildAdminNav('super_admin')
    expect(items.map((item) => item.key)).toEqual(['dashboard', 'memory', 'knowledge', 'settings', 'users'])
  })

  it('resolves a valid landing page for admin roles', () => {
    expect(resolveAdminHome('admin')).toBe('/dashboard')
    expect(resolveAdminHome('super_admin')).toBe('/dashboard')
  })
})
