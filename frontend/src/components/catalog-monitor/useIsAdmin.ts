import { useAuthStore } from '@/store/authStore'

/** Approving, sending to Amazon and loading a reference file are admin actions. */
export const useIsAdmin = () => useAuthStore((s) => s.organization?.my_role) === 'admin'
