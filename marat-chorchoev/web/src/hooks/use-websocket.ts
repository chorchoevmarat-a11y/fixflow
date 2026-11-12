'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import { getToken, getOrgId } from '@/lib/auth'

interface UseWebSocketOptions {
  onMessage?: (event: MessageEvent) => void
  onError?: (event: Event) => void
  autoReconnect?: boolean
  reconnectInterval?: number
}

export function useWebSocket(urlSuffix: string = '/ws', options: UseWebSocketOptions = {}) {
  const { onMessage, onError, autoReconnect = true, reconnectInterval = 5000 } = options
  const [isConnected, setIsConnected] = useState(false)
  const [lastMessage, setLastMessage] = useState<unknown | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)

  const connect = useCallback(() => {
    const token = getToken()
    const orgId = getOrgId()
    const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
    const wsUrl = baseUrl.replace(/^http/, 'ws') + '/api/v1' + urlSuffix + (token ? `?token=${token}` : '')

    try {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        setIsConnected(true)
        if (orgId) {
          ws.send(JSON.stringify({ type: 'subscribe_org', org_id: orgId }))
        }
      }

      ws.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data)
          setLastMessage(parsed)
        } catch {
          setLastMessage(event.data)
        }
        onMessage?.(event)
      }

      ws.onerror = (event) => {
        onError?.(event)
      }

      ws.onclose = () => {
        setIsConnected(false)
        if (autoReconnect) {
          reconnectTimeoutRef.current = setTimeout(() => {
            connect()
          }, reconnectInterval)
        }
      }
    } catch {
      setIsConnected(false)
    }
  }, [urlSuffix, onMessage, onError, autoReconnect, reconnectInterval])

  useEffect(() => {
    connect()
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [connect])

  const sendMessage = useCallback((msg: unknown) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(typeof msg === 'string' ? msg : JSON.stringify(msg))
    }
  }, [])

  return { isConnected, lastMessage, sendMessage }
}
