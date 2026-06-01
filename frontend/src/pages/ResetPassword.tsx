import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import axios from 'axios'
import { ArrowLeft, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { PasswordInput } from '@/components/PasswordInput'
import AuthLayout from '@/components/AuthLayout'
import { useToast } from '@/components/ui/use-toast'
import { authApi } from '@/services/api'
import { useTranslation } from '@/i18n'

export default function ResetPassword() {
  const [isLoading, setIsLoading] = useState(false)
  const [tokenError, setTokenError] = useState(false)
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const { toast } = useToast()
  const { t } = useTranslation()

  const token = searchParams.get('token')

  const schema = z
    .object({
      new_password: z.string().min(8, t('resetPassword.passwordMin')),
      confirm_password: z.string(),
    })
    .refine((data) => data.new_password === data.confirm_password, {
      message: t('resetPassword.passwordsMismatch'),
      path: ['confirm_password'],
    })

  type ResetForm = z.infer<typeof schema>

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ResetForm>({
    resolver: zodResolver(schema),
  })

  const onSubmit = async (data: ResetForm) => {
    if (!token) return
    setIsLoading(true)
    setTokenError(false)
    try {
      await authApi.resetPassword(token, data.new_password)
      toast({
        title: t('resetPassword.successTitle'),
        description: t('resetPassword.successDesc'),
      })
      navigate('/login')
    } catch (error: unknown) {
      if (axios.isAxiosError(error) && error.response?.status === 400) {
        setTokenError(true)
      } else {
        toast({
          variant: 'destructive',
          title: t('resetPassword.failedTitle'),
          description: t('resetPassword.failedDesc'),
        })
      }
    } finally {
      setIsLoading(false)
    }
  }

  if (!token) {
    return (
      <AuthLayout>
        <div className="space-y-6 text-center">
          <div className="space-y-2">
            <h2 className="text-2xl font-bold tracking-tight">{t('resetPassword.invalidTitle')}</h2>
            <p className="text-sm text-muted-foreground">{t('resetPassword.invalidDesc')}</p>
          </div>
          <Link to="/forgot-password" className="inline-flex items-center text-sm text-primary hover:underline">
            <ArrowLeft className="mr-1 h-4 w-4" />
            {t('resetPassword.requestNew')}
          </Link>
        </div>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout>
      <div className="space-y-6">
        <div className="space-y-2">
          <span className="text-2xl font-bold text-primary lg:hidden">Inthezon</span>
          <h2 className="text-2xl font-bold tracking-tight">{t('resetPassword.title')}</h2>
          <p className="text-sm text-muted-foreground">{t('resetPassword.subtitle')}</p>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="new_password">{t('resetPassword.newPassword')}</Label>
            <PasswordInput
              id="new_password"
              autoComplete="new-password"
              placeholder={t('resetPassword.newPasswordPlaceholder')}
              {...register('new_password')}
            />
            {errors.new_password && (
              <p className="text-sm text-destructive">{errors.new_password.message}</p>
            )}
          </div>
          <div className="space-y-2">
            <Label htmlFor="confirm_password">{t('resetPassword.confirmPassword')}</Label>
            <PasswordInput
              id="confirm_password"
              autoComplete="new-password"
              placeholder={t('resetPassword.confirmPlaceholder')}
              {...register('confirm_password')}
            />
            {errors.confirm_password && (
              <p className="text-sm text-destructive">{errors.confirm_password.message}</p>
            )}
          </div>
          {tokenError && (
            <p className="text-sm text-destructive">{t('resetPassword.invalidToken')}</p>
          )}
          <Button
            type="submit"
            className="w-full bg-blue-950 text-white transition-colors hover:bg-blue-900 active:scale-[0.99]"
            disabled={isLoading}
          >
            {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('resetPassword.submit')}
          </Button>
          <Link to="/login" className="flex items-center justify-center text-sm text-primary hover:underline">
            <ArrowLeft className="mr-1 h-4 w-4" />
            {t('resetPassword.backToLogin')}
          </Link>
        </form>
      </div>
    </AuthLayout>
  )
}
