import { useTranslation } from '@/i18n'

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  const { t } = useTranslation()

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[2fr_3fr]">
      {/* Brand panel — hidden on mobile */}
      <div className="relative hidden overflow-hidden bg-gradient-to-br from-slate-900 via-blue-950 to-indigo-950 lg:flex lg:flex-col lg:justify-between lg:p-12 text-white">
        <div className="absolute -right-24 -top-24 h-96 w-96 rounded-full bg-white/5 blur-3xl" />
        <div className="absolute -bottom-32 -left-16 h-96 w-96 rounded-full bg-white/5 blur-3xl" />
        <span className="relative text-3xl font-bold tracking-tight">Inthezon</span>
        <p className="relative max-w-sm text-2xl font-medium leading-snug text-white/90">{t('login.brandTagline')}</p>
        <p className="relative text-sm text-white/50">{t('login.brandFootnote')}</p>
      </div>

      {/* Form panel */}
      <div className="flex min-h-screen items-center justify-center bg-background px-4 py-12 lg:min-h-0">
        <div className="w-full max-w-md">{children}</div>
      </div>
    </div>
  )
}
