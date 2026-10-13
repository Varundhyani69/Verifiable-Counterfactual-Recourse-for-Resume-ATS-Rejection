import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useSession } from '../session'
import { getEvidence, patchFact } from '../api/candidates'
import { runAnalysis } from '../api/analysis'
import { queryKeys } from '../queryKeys'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { ErrorBanner } from '../components/ErrorBanner'
import type { CandidateFactResponse } from '../types/candidate'
import styles from './CandidateEvidenceReviewScreen.module.css'

const VERIFICATION_OPTIONS = [
  'Supported',
  'Partially Supported',
  'Unsupported',
  'Needs Confirmation',
]

function claimTypeBadgeClass(claimType: string): string {
  const map: Record<string, string> = {
    skill: styles.badgeSkill,
    project: styles.badgeProject,
    responsibility: styles.badgeResponsibility,
    certification: styles.badgeCertification,
    experience: styles.badgeExperience,
    achievement: styles.badgeAchievement,
  }
  return map[claimType] ?? ''
}

function statusBadgeClass(status: string): string {
  if (status === 'Supported') return styles.statusSupported
  if (status === 'Partially Supported') return styles.statusPartially
  if (status === 'Unsupported') return styles.statusUnsupported
  return styles.statusNeeds
}

function FactCard({ fact, candidateId }: { fact: CandidateFactResponse; candidateId: string }) {
  const queryClient = useQueryClient()
  const [showOriginal, setShowOriginal] = useState(false)
  const [editText, setEditText] = useState(fact.claim_text)
  const [editStatus, setEditStatus] = useState(fact.verification_status)

  const patchMutation = useMutation({
    mutationFn: () =>
      patchFact(candidateId, fact.id, {
        claim_text: editText,
        verification_status: editStatus,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.evidence(candidateId) })
    },
  })

  return (
    <div className={styles.card}>
      <div>
        <span className={`${styles.badge} ${claimTypeBadgeClass(fact.claim_type)}`}>
          {fact.claim_type}
        </span>
        <span className={`${styles.badge} ${statusBadgeClass(fact.verification_status)}`}>
          {fact.verification_status}
        </span>
      </div>
      <p>{fact.claim_text}</p>
      <button
        type="button"
        className={styles.toggleBtn}
        onClick={() => setShowOriginal(s => !s)}
      >
        {showOriginal ? 'Hide original' : 'Show original'}
      </button>
      {showOriginal && (
        <div className={styles.originalText}>
          <strong>Original:</strong> {fact.original_claim_text}
        </div>
      )}
      <div className={styles.editForm}>
        <input
          type="text"
          aria-label="Edit claim text"
          value={editText}
          onChange={e => setEditText(e.target.value)}
        />
        <select
          aria-label="Verification status"
          value={editStatus}
          onChange={e => setEditStatus(e.target.value)}
        >
          {VERIFICATION_OPTIONS.map(opt => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
        <button
          type="button"
          className={styles.saveBtn}
          onClick={() => patchMutation.mutate()}
          disabled={patchMutation.isPending}
        >
          Save
        </button>
      </div>
      {patchMutation.isError && (
        <ErrorBanner message={(patchMutation.error as Error).message} />
      )}
    </div>
  )
}

export function CandidateEvidenceReviewScreen() {
  const navigate = useNavigate()
  const { session, setSession } = useSession()
  const candidateId = session.candidateId

  const evidenceQuery = useQuery({
    queryKey: queryKeys.evidence(candidateId ?? ''),
    queryFn: () => getEvidence(candidateId!),
    enabled: !!candidateId,
  })

  const analysisMutation = useMutation({
    mutationFn: () => runAnalysis(session.resumeId!, session.jobDescriptionId!),
    onSuccess: data => {
      setSession({ resumeVersionId: data.resume_version_id, analysisResult: data })
      navigate('/analysis')
    },
  })

  // Guard: candidateId is set by ResumeJDInputScreen after a successful resume upload.
  // SessionGuard only checks resumeId and jobDescriptionId, so we guard here too.
  if (!candidateId) {
    return (
      <ErrorBanner message="Session is missing candidate information. Please start over from the input screen." />
    )
  }

  if (evidenceQuery.isLoading) return <LoadingSpinner />
  if (evidenceQuery.isError) {
    return (
      <ErrorBanner
        message={(evidenceQuery.error as Error).message}
        onRetry={() => evidenceQuery.refetch()}
      />
    )
  }

  const facts = evidenceQuery.data?.facts ?? []

  return (
    <div className={styles.container}>
      <h1>Candidate Evidence Review</h1>
      <p>Review and edit the facts extracted from your resume.</p>

      {facts.length === 0 && <p>No facts extracted from this resume.</p>}

      {facts.map(fact => (
        <FactCard key={fact.id} fact={fact} candidateId={candidateId} />
      ))}

      {analysisMutation.isError && (
        <ErrorBanner message={(analysisMutation.error as Error).message} />
      )}

      {analysisMutation.isPending && <LoadingSpinner />}

      <button
        type="button"
        className={styles.continueBtn}
        onClick={() => analysisMutation.mutate()}
        disabled={analysisMutation.isPending}
      >
        Continue to Analysis
      </button>
    </div>
  )
}
