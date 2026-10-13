import React, { createContext, useContext, useState, useCallback } from 'react'
import type { AnalysisResponse } from './types/analysis'
import type { RecourseGenerateResponse } from './types/recourse'

export interface Session {
  resumeId?: string
  candidateId?: string
  jobDescriptionId?: string
  resumeVersionId?: string
  recourseId?: string
  analysisResult?: AnalysisResponse
  recourseResult?: RecourseGenerateResponse
}

interface SessionContextValue {
  session: Session
  setSession: (patch: Partial<Session>) => void
  clearSession: () => void
}

const STORAGE_KEY = 'ats_session'

function loadSession(): Session {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as Session) : {}
  } catch {
    return {}
  }
}

export const SessionContext = createContext<SessionContextValue>({
  session: {},
  setSession: () => {},
  clearSession: () => {},
})

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [session, setSessionState] = useState<Session>(loadSession)

  const setSession = useCallback((patch: Partial<Session>) => {
    setSessionState(prev => {
      const next = { ...prev, ...patch }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
      return next
    })
  }, [])

  const clearSession = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY)
    setSessionState({})
  }, [])

  return (
    <SessionContext.Provider value={{ session, setSession, clearSession }}>
      {children}
    </SessionContext.Provider>
  )
}

export function useSession() {
  return useContext(SessionContext)
}
