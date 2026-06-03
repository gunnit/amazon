import { Link } from 'react-router-dom'
import { Compass, Home } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useTranslation } from '@/i18n'

export default function NotFound() {
  const { t } = useTranslation()

  return (
    <div className="mx-auto flex min-h-[60vh] max-w-md flex-col items-center justify-center text-center">
      <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
        <Compass className="h-7 w-7" />
      </div>
      <p className="text-5xl font-bold tracking-tight">404</p>
      <h1 className="mt-2 text-xl font-semibold">{t('notFound.title')}</h1>
      <p className="mt-1 text-sm text-muted-foreground">{t('notFound.description')}</p>
      <Button asChild className="mt-6">
        <Link to="/">
          <Home className="mr-2 h-4 w-4" />
          {t('notFound.backToDashboard')}
        </Link>
      </Button>
    </div>
  )
}
