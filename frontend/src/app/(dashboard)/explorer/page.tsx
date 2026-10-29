'use client'
import { AppShell } from '@/components/layout/AppShell'
import { Explorer } from '@/components/databridge/Explorer'

export default function ExplorerPage() {
  return <AppShell><div className="flex-1 overflow-y-auto"><Explorer /></div></AppShell>
}
