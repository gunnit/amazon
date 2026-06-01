import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { PasswordInput } from '@/components/PasswordInput'
import AuthLayout from '@/components/AuthLayout'
import { useToast } from '@/components/ui/use-toast'
import { useAuthStore } from '@/store/authStore'
import { useTranslation } from '@/i18n'

export default function Login() {
  const [isLoading, setIsLoading] = useState(false)
  const [showWarmupHint, setShowWarmupHint] = useState(false)
  const navigate = useNavigate()
  const { toast } = useToast()
  const { login } = useAuthStore()
  const { t } = useTranslation()

  // Show a "server warming up" hint if login takes longer than 4s — common on
  // Render free tier after a cold start. Resets when loading finishes.
  useEffect(() => {
    if (!isLoading) {
      setShowWarmupHint(false)
      return
    }
    const timer = setTimeout(() => setShowWarmupHint(true), 4000)
    return () => clearTimeout(timer)
  }, [isLoading])

  const loginSchema = z.object({
    email: z.string().email(t('login.invalidEmail')),
    password: z.string().min(1, t('login.passwordRequired')),
  })

  type LoginForm = z.infer<typeof loginSchema>

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
  })

  const onSubmit = async (data: LoginForm) => {
    setIsLoading(true)
    try {
      await login(data.email, data.password)
      toast({
        title: t('login.successTitle'),
        description: t('login.successDesc'),
      })
      navigate('/')
    } catch (error: unknown) {
      toast({
        variant: 'destructive',
        title: t('login.failedTitle'),
        description: t('login.failedDesc'),
      })
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <AuthLayout>
      <div className="space-y-6">
        <div className="space-y-2">
          <span className="text-2xl font-bold text-primary lg:hidden">Inthezon</span>
          <h2 className="text-2xl font-bold tracking-tight">{t('login.welcomeBack')}</h2>
          <p className="text-sm text-muted-foreground">{t('login.subtitle')}</p>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="email">{t('common.email')}</Label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              placeholder={t('login.emailPlaceholder')}
              {...register('email')}
            />
            {errors.email && (
              <p className="text-sm text-destructive">{errors.email.message}</p>
            )}
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="password">{t('common.password')}</Label>
              <Link to="/forgot-password" className="text-sm text-primary hover:underline">
                {t('login.forgotPassword')}
              </Link>
            </div>
            <PasswordInput
              id="password"
              autoComplete="current-password"
              placeholder={t('login.passwordPlaceholder')}
              {...register('password')}
            />
            {errors.password && (
              <p className="text-sm text-destructive">{errors.password.message}</p>
            )}
          </div>
          <Button
            type="submit"
            className="w-full bg-blue-950 text-white transition-colors hover:bg-blue-900 active:scale-[0.99]"
            disabled={isLoading}
          >
            {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {isLoading ? t('login.signingIn') : t('login.signIn')}
          </Button>
          {showWarmupHint && (
            <p className="text-xs text-center text-muted-foreground animate-in fade-in">
              {t('login.warmupHint')}
            </p>
          )}
          <p className="text-sm text-center text-muted-foreground">
            {t('login.noAccount')}{' '}
            <Link to="/register" className="text-primary hover:underline">
              {t('login.signUp')}
            </Link>
          </p>
        </form>
      </div>
    </AuthLayout>
  )
}
