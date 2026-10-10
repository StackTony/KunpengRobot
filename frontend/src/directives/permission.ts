/* v-permission 指令：无权限时移除元素 */
import type { Directive } from 'vue'
import { useRbacStore } from '@/stores/rbac'

function check(value: string | string[]): boolean {
  const perms = Array.isArray(value) ? value : [value]
  const rbac = useRbacStore()
  return perms.every((p) => rbac.hasPerm(p))
}

export const permissionDirective: Directive<HTMLElement, string | string[]> = {
  mounted(el, binding) {
    if (!check(binding.value)) el.parentNode?.removeChild(el)
  },
  updated(el, binding) {
    if (!check(binding.value)) el.parentNode?.removeChild(el)
  },
}
