import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useSession } from '../session'
import { ExplanationCard } from '../components/ExplanationCard'
import { ErrorBanner } from '../components/ErrorBanner'
import type { ProposedEditResponse } from '../types/recourse'
import styles from './CounterfactualRecommendationsScreen.module.css'

export function CounterfactualRecommendationsScreen() {
  const navigate = useNavigate()
  const { session } = useSession()
  const recourseResult = session.recourseResult

  const initialEdits = recourseResult?.accepted_edits ?? []
  const [acceptedEdits, setAcceptedEdits] = useState<ProposedEditResponse[]>(initialEdits)

  if (!recourseResult) {
    return <ErrorBanner message="No recourse result found. Please go back to Analysis." />
  }

  const isInfeasible = recourseResult.status === 'infeasible'
  const threshold = session.analysisResult?.score_breakdown.threshold ?? 0.5
  const baseScore = session.analysisResult?.score_breakdown.total_score ?? 0

  const totalEditCost = acceptedEdits.reduce((s, e) => s + e.edit_cost, 0)
  const projectedScore = Math.min(
    1,
    Math.max(0, baseScore + acceptedEdits.reduce((s, e) => s + e.score_contribution, 0)),
  )
  const projectedDecision = projectedScore >= threshold ? 'pass' : 'fail'
  const supported = acceptedEdits.filter(e => e.verification_status === 'Supported').length
  const groundingRate = acceptedEdits.length > 0 ? supported / acceptedEdits.length : 0

  function handleConfirm(editId: string) {
    setAcceptedEdits(prev =>
      prev.map(e =>
        e.id === editId ? { ...e, verification_status: 'Supported' } : e,
      ),
    )
  }

  function handleReject(editId: string) {
    setAcceptedEdits(prev => prev.filter(e => e.id !== editId))
  }

  return (
    <div className={styles.container}>
      <h1>Counterfactual Recommendations</h1>

      {isInfeasible && (
        <ErrorBanner
          message={`${recourseResult.reason ?? 'Infeasible'}: ${recourseResult.detail ?? ''}`}
        />
      )}

      <div className={styles.metricsPanel}>
        <div className={styles.metricItem}>
          <div className={styles.metricValue}>{totalEditCost.toFixed(2)}</div>
          <div className={styles.metricLabel}>Total Edit Cost</div>
        </div>
        <div className={styles.metricItem}>
          <div className={styles.metricValue}>{Math.round(projectedScore * 100)}%</div>
          <div className={styles.metricLabel}>Projected Score</div>
        </div>
        <div className={styles.metricItem}>
          <div className={styles.metricValue}>{projectedDecision.toUpperCase()}</div>
          <div className={styles.metricLabel}>Projected Decision</div>
        </div>
        <div className={styles.metricItem}>
          <div className={styles.metricValue}>{Math.round(groundingRate * 100)}%</div>
          <div className={styles.metricLabel}>Grounding Rate</div>
        </div>
      </div>

      {acceptedEdits.length === 0 && !isInfeasible && (
        <p>No accepted edits to display.</p>
      )}

      {acceptedEdits.map(edit => (
        <ExplanationCard
          key={edit.id}
          edit={edit}
          onConfirm={handleConfirm}
          onReject={handleReject}
        />
      ))}

      {isInfeasible && recourseResult.partial_result && recourseResult.partial_result.edits.length > 0 && (
        <div className={styles.partialSection}>
          <h2>Partial Edits</h2>
          {recourseResult.partial_result.edits.map(edit => (
            <ExplanationCard
              key={edit.id}
              edit={edit}
              onConfirm={() => {}}
              onReject={() => {}}
            />
          ))}
        </div>
      )}

      <button
        type="button"
        className={styles.acceptBtn}
        onClick={() => navigate('/comparison')}
      >
        Accept &amp; Generate Resume
      </button>
    </div>
  )
}
