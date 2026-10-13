import { useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useSession } from './session'

interface Props {
  children: React.ReactNode
}

export function SessionGuard({ children }: Props) {
  const { session } = useSession()
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    if (!session.resumeId || !session.jobDescriptionId) {
      const redirect = encodeURIComponent(location.pathname)
      navigate(`/input?redirect=${redirect}`, { replace: true })
    }
  }, [session.resumeId, session.jobDescriptionId, navigate, location.pathname])

  if (!session.resumeId || !session.jobDescriptionId) {
    return <p>Please upload a resume and job description first</p>
  }

  return <>{children}</>
}
