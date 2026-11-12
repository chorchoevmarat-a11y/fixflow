'use client'

import React, { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useAuth } from '@/hooks/use-auth'
import { setOrgId } from '@/lib/auth'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { Organization } from '@/types'

const loginSchema = z.object({
  email: z.string().email('Please enter a valid email'),
  password: z.string().min(1, 'Password is required'),
})

type LoginValues = z.infer<typeof loginSchema>

export default function LoginPage() {
  const router = useRouter()
  const { login } = useAuth()
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [organizations, setOrganizations] = useState<Organization[] | null>(null)
  const [selectedOrgId, setSelectedOrgId] = useState<string>('')

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      email: '',
      password: '',
    },
  })

  const onSubmit = async (data: LoginValues) => {
    setError(null)
    setLoading(true)
    try {
      const orgs = await login(data.email, data.password)
      if (orgs && orgs.length > 1) {
        setOrganizations(orgs)
        setSelectedOrgId(orgs[0].id)
      } else if (orgs && orgs.length === 1) {
        setOrgId(orgs[0].id)
        router.push('/dashboard')
      } else {
        router.push('/dashboard')
      }
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail || 'Failed to sign in. Please verify your credentials.'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  const handleOrgConfirm = () => {
    if (selectedOrgId) {
      setOrgId(selectedOrgId)
      router.push('/dashboard')
    }
  }

  return (
    <Card className="shadow-lg border-muted">
      <CardHeader className="space-y-1">
        <CardTitle className="text-xl">Sign in to your account</CardTitle>
        <CardDescription>
          Enter your email and password to access the portal
        </CardDescription>
      </CardHeader>
      <CardContent>
        {error && (
          <Alert variant="destructive" className="mb-4">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {organizations ? (
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>Select Organization</Label>
              <Select
                value={selectedOrgId}
                onValueChange={(val) => setSelectedOrgId(val)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select an organization" />
                </SelectTrigger>
                <SelectContent>
                  {organizations.map((org) => (
                    <SelectItem key={org.id} value={org.id}>
                      {org.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button
              onClick={handleOrgConfirm}
              className="w-full"
              disabled={!selectedOrgId}
            >
              Continue to Dashboard
            </Button>
          </div>
        ) : (
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email">Email address</Label>
              <Input
                id="email"
                type="email"
                placeholder="dispatcher@fixflow.com"
                {...register('email')}
                disabled={loading}
              />
              {errors.email && (
                <p className="text-xs text-destructive">{errors.email.message}</p>
              )}
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="password">Password</Label>
              </div>
              <Input
                id="password"
                type="password"
                placeholder="••••••••"
                {...register('password')}
                disabled={loading}
              />
              {errors.password && (
                <p className="text-xs text-destructive">
                  {errors.password.message}
                </p>
              )}
            </div>

            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? 'Signing in...' : 'Sign in'}
            </Button>
          </form>
        )}
      </CardContent>
      <CardFooter className="flex justify-center border-t py-3 text-xs text-muted-foreground">
        FixFlow v0.1.0 • Enterprise Maintenance System
      </CardFooter>
    </Card>
  )
}
