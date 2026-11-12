import React from 'react'
import { Wrench } from 'lucide-react'

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className="min-h-screen flex flex-col justify-center items-center bg-muted/40 p-4 sm:p-8">
      <div className="w-full max-w-md space-y-6">
        <div className="flex items-center justify-center space-x-2 text-primary font-bold text-2xl tracking-tight">
          <div className="p-2 bg-primary rounded-lg text-primary-foreground shadow">
            <Wrench className="w-6 h-6" />
          </div>
          <span>FixFlow</span>
        </div>
        {children}
      </div>
    </div>
  )
}
