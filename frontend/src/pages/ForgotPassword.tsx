import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { ArrowLeft, Loader2, MailCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import AuthLayout from '@/components/AuthLayout'
import { authApi } from '@/services/api'
import { useTranslation } from '@/i18n'

export default function ForgotPassword() {
  const [isLoading, setIsLoading] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const { t } = useTranslation()

  const schema = z.object({
    email: z.string().email(t('login.invalidEmail')),
  })

  type ForgotForm = z.infer<typeof schema>

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ForgotForm>({
    resolver: zodResolver(schema),
  })

  const onSubmit = async (data: ForgotForm) => {
    setIsLoading(true)
    try {
      await authApi.forgotPassword(data.email)
    } catch {
      // The endpoint always returns 200; treat any failure as success to avoid
      // leaking whether an account exists.
    } finally {
      setIsLoading(false)
      setSubmitted(true)
    }
  }

  return (
    <AuthLayout>
      {submitted ? (
        <div className="space-y-6 text-center">
          <div className="flex justify-center">
            <MailCheck className="h-12 w-12 text-primary" />
          </div>
          <div className="space-y-2">
            <h2 className="text-2xl font-bold tracking-tight">{t('forgotPassword.sentTitle')}</h2>
            <p className="text-sm text-muted-foreground">{t('forgotPassword.sentDesc')}</p>
          </div>
          <Link to="/login" className="inline-flex items-center text-sm text-primary hover:underline">
            <ArrowLeft className="mr-1 h-4 w-4" />
            {t('forgotPassword.backToLogin')}
          </Link>
        </div>
      ) : (
        <div className="space-y-6">
          <div className="space-y-2">
            <span className="text-2xl font-bold text-primary lg:hidden">Inthezon</span>
            <h2 className="text-2xl font-bold tracking-tight">{t('forgotPassword.title')}</h2>
            <p className="text-sm text-muted-foreground">{t('forgotPassword.subtitle')}</p>
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
            <Button
              type="submit"
              className="w-full bg-blue-950 text-white transition-colors hover:bg-blue-900 active:scale-[0.99]"
              disabled={isLoading}
            >
              {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t('forgotPassword.submit')}
            </Button>
            <Link to="/login" className="flex items-center justify-center text-sm text-primary hover:underline">
              <ArrowLeft className="mr-1 h-4 w-4" />
              {t('forgotPassword.backToLogin')}
            </Link>
          </form>
        </div>
      )}
    </AuthLayout>
  )
}
