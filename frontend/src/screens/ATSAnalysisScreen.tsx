import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { useSession } from '../session'
import { generateRecourse } from '../api/recourse'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { ErrorBanner } from '../components/ErrorBanner'
import styles from './ATSAnalysisScreen.module.css'

export function ATSAnalysisScreen() {
  const navigate = useNavigate()
  const { session, setSession } = useSession()
  const result = session.analysisResult

  const recourseMutation = useMutation({
    mutationFn: () =>
      generateRecourse(session.resumeVersionId!, session.jobDescriptionId!),
    onSuccess: data => {
      setSession({ recourseId: data.recourse_id, recourseResult: data })
      navigate('/recommendations')
    },
  })

  if (!result) {
    return (
      <ErrorBanner message="No analysis result found. Please go back to Evidence Review." />
    )
  }

  const sb = result.score_breakdown
  const pct = Math.round(sb.total_score * 100)
  const isPassing = result.decision === 'pass'

  return (
    <div className={styles.container}>
      <h1>ATS Analysis Result</h1>

      <div className={`${styles.scoreCircle} ${isPassing ? styles.scorePass : styles.scoreFail}`}>
        {pct}%
      </div>

      <div style={{ textAlign: 'center' }}>
        <span className={`${styles.decisionBadge} ${isPassing ? styles.decisionPass : styles.decisionFail}`}>
          {result.decision.toUpperCase()}
        </span>
      </div>

      <div className={styles.metricRow}>
        <span className={styles.metricLabel}>Skill Overlap</span>
        <div className={styles.progressBar}>
          <div
            className={styles.progressFill}
            style={{ width: `${Math.round(sb.skill_overlap_score * 100)}%` }}
          />
        </div>
        <span className={styles.metricValue}>{Math.round(sb.skill_overlap_score * 100)}%</span>
      </div>

      <div className={styles.metricRow}>
        <span className={styles.metricLabel}>Semantic Similarity</span>
        <div className={styles.progressBar}>
          <div
            className={styles.progressFill}
            style={{ width: `${Math.round(sb.semantic_similarity_score * 100)}%` }}
          />
        </div>
        <span className={styles.metricValue}>{Math.round(sb.semantic_similarity_score * 100)}%</span>
      </div>

      <p>
        <strong>Weights:</strong> Skill Overlap {Math.round((sb.weights['skill_overlap'] ?? 0) * 100)}%,
        SBERT {Math.round((sb.weights['sbert'] ?? 0) * 100)}%
      </p>
      <p><strong>Threshold:</strong> {Math.round(sb.threshold * 100)}%</p>

      <p className={styles.disclosure}>{result.disclosure}</p>

      {recourseMutation.isError && (
        <ErrorBanner message={(recourseMutation.error as Error).message} />
      )}
      {recourseMutation.isPending && <LoadingSpinner />}

      <button
        type="button"
        className={styles.generateBtn}
        onClick={() => recourseMutation.mutate()}
        disabled={recourseMutation.isPending}
      >
        Generate Recommendations
      </button>
    </div>
  )
}
