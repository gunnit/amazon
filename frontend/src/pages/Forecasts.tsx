import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Area,
  AreaChart,
} from 'recharts'
import { TrendingUp, RefreshCw, Loader2, Calendar, Target } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/use-toast'
import { forecastsApi, accountsApi } from '@/services/api'
import { formatCurrency, formatDate } from '@/lib/utils'
import type { Forecast, AmazonAccount } from '@/types'

export default function Forecasts() {
  const [selectedAccount, setSelectedAccount] = useState<string>('')
  const [forecastHorizon, setForecastHorizon] = useState('30')
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const { data: accounts } = useQuery<AmazonAccount[]>({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  })

  const { data: forecasts, isLoading } = useQuery<Forecast[]>({
    queryKey: ['forecasts'],
    queryFn: () => forecastsApi.list(),
  })

  const generateMutation = useMutation({
    mutationFn: (params: { account_id: string; horizon_days: number }) =>
      forecastsApi.generate(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['forecasts'] })
      toast({ title: 'Forecast generated successfully' })
    },
    onError: () => {
      toast({
        variant: 'destructive',
        title: 'Failed to generate forecast',
      })
    },
  })

  const handleGenerate = () => {
    if (!selectedAccount) {
      toast({
        variant: 'destructive',
        title: 'Please select an account',
      })
      return
    }

    generateMutation.mutate({
      account_id: selectedAccount,
      horizon_days: parseInt(forecastHorizon),
    })
  }

  // Get the latest forecast for display
  const latestForecast = forecasts?.[0]

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Forecasts</h1>
          <p className="text-muted-foreground">
            AI-powered sales predictions and trend analysis
          </p>
        </div>
      </div>

      {/* Generate Forecast */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Target className="h-5 w-5" />
            Generate New Forecast
          </CardTitle>
          <CardDescription>
            Create sales predictions using machine learning models
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-end gap-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Account</label>
              <Select value={selectedAccount} onValueChange={setSelectedAccount}>
                <SelectTrigger className="w-[200px]">
                  <SelectValue placeholder="Select account" />
                </SelectTrigger>
                <SelectContent>
                  {accounts?.map((account) => (
                    <SelectItem key={account.id} value={account.id}>
                      {account.account_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Forecast Horizon</label>
              <Select value={forecastHorizon} onValueChange={setForecastHorizon}>
                <SelectTrigger className="w-[150px]">
                  <Calendar className="mr-2 h-4 w-4" />
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="30">30 days</SelectItem>
                  <SelectItem value="60">60 days</SelectItem>
                  <SelectItem value="90">90 days</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Button
              onClick={handleGenerate}
              disabled={generateMutation.isPending || !selectedAccount}
            >
              {generateMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="mr-2 h-4 w-4" />
              )}
              Generate Forecast
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Forecast Display */}
      {isLoading ? (
        <div className="flex items-center justify-center h-64">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      ) : latestForecast ? (
        <div className="grid gap-4 md:grid-cols-3">
          {/* Forecast Chart */}
          <Card className="col-span-2">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle>Sales Forecast</CardTitle>
                  <CardDescription>
                    {latestForecast.horizon_days}-day prediction using {latestForecast.model_used}
                  </CardDescription>
                </div>
                <Badge variant="secondary">
                  {(latestForecast.confidence_interval * 100).toFixed(0)}% CI
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <div className="h-[400px]">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={latestForecast.predictions}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis
                      dataKey="date"
                      tickFormatter={(value) =>
                        new Date(value).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
                      }
                    />
                    <YAxis tickFormatter={(value) => `$${(value / 1000).toFixed(0)}k`} />
                    <Tooltip
                      formatter={(value: number) => [formatCurrency(value)]}
                      labelFormatter={(label) => formatDate(label)}
                    />
                    <Area
                      type="monotone"
                      dataKey="upper_bound"
                      stroke="none"
                      fill="hsl(var(--primary))"
                      fillOpacity={0.1}
                    />
                    <Area
                      type="monotone"
                      dataKey="lower_bound"
                      stroke="none"
                      fill="white"
                    />
                    <Line
                      type="monotone"
                      dataKey="predicted_value"
                      stroke="hsl(var(--primary))"
                      strokeWidth={2}
                      dot={false}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>

          {/* Forecast Stats */}
          <div className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium">Model Accuracy</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">MAPE</span>
                      <span className="font-medium">
                        {latestForecast.mape?.toFixed(2) || 'N/A'}%
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">
                      Mean Absolute Percentage Error
                    </p>
                  </div>
                  <div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">RMSE</span>
                      <span className="font-medium">
                        {formatCurrency(latestForecast.rmse || 0)}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">
                      Root Mean Square Error
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium">Forecast Summary</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Generated</span>
                    <span>{formatDate(latestForecast.generated_at)}</span>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Model</span>
                    <Badge variant="outline">{latestForecast.model_used}</Badge>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Horizon</span>
                    <span>{latestForecast.horizon_days} days</span>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Type</span>
                    <span className="capitalize">{latestForecast.forecast_type}</span>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <TrendingUp className="h-4 w-4" />
                  Predicted Total
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold">
                  {formatCurrency(
                    latestForecast.predictions.reduce((sum, p) => sum + p.predicted_value, 0)
                  )}
                </div>
                <p className="text-sm text-muted-foreground mt-1">
                  Next {latestForecast.horizon_days} days
                </p>
              </CardContent>
            </Card>
          </div>
        </div>
      ) : (
        <Card>
          <CardContent className="py-10 text-center">
            <TrendingUp className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
            <p className="text-muted-foreground">
              No forecasts generated yet. Select an account and generate your first prediction.
            </p>
          </CardContent>
        </Card>
      )}

      {/* Previous Forecasts */}
      {forecasts && forecasts.length > 1 && (
        <Card>
          <CardHeader>
            <CardTitle>Previous Forecasts</CardTitle>
            <CardDescription>History of generated predictions</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {forecasts.slice(1, 6).map((forecast) => (
                <div
                  key={forecast.id}
                  className="flex items-center justify-between py-2 border-b last:border-0"
                >
                  <div className="flex items-center gap-4">
                    <Badge variant="outline">{forecast.model_used}</Badge>
                    <span className="text-sm">
                      {forecast.horizon_days}-day {forecast.forecast_type} forecast
                    </span>
                  </div>
                  <span className="text-sm text-muted-foreground">
                    {formatDate(forecast.generated_at)}
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
