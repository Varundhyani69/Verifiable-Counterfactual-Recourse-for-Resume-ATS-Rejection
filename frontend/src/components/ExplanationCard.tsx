import { useMutation } from '@tanstack/react-query'
import { updateEditStatus } from '../api/recourse'
import type { ProposedEditResponse } from '../types/recourse'
import styles from './ExplanationCard.module.css'

interface Props {
  edit: ProposedEditResponse
  onConfirm: (editId: string) => void
  onReject: (editId: string) => void
}

function statusBadgeClass(status: string): string {
  if (status === 'Supported') return styles.badgeSupported
  if (status === 'Partially Supported') return styles.badgePartial
  if (status === 'Unsupported') return styles.badgeUnsupported
  return styles.badgeNeeds
}

export function ExplanationCard({ edit, onConfirm, onReject }: Props) {
  const isNeedsConfirmation = edit.verification_status === 'Needs Confirmation'

  const confirmMutation = useMutation({
    mutationFn: () => updateEditStatus(edit.id, 'confirm'),
    onSuccess: () => onConfirm(edit.id),
  })

  const rejectMutation = useMutation({
    mutationFn: () => updateEditStatus(edit.id, 'reject'),
    onSuccess: () => onReject(edit.id),
  })

  const isActing = confirmMutation.isPending || rejectMutation.isPending

  return (
    <div
      className={`${styles.card} ${isNeedsConfirmation ? styles.cardNeedsConfirmation : ''}`}
      data-testid="explanation-card"
    >
      <div>
        <span className={`${styles.badge} ${statusBadgeClass(edit.verification_status)}`}>
          {edit.verification_status}
        </span>
        <span className={styles.badge}>{edit.edit_type}</span>
      </div>

      <p>{edit.proposed_text}</p>
      <p style={{ color: '#6b7280', fontSize: '0.85rem' }}>
        <em>Original:</em> {edit.original_text}
      </p>

      <div className={styles.label}>Why this helps</div>
      <p style={{ fontSize: '0.9rem' }}>This edit improves ATS alignment by addressing job requirements.</p>

      {edit.evidence_fact_ids.length > 0 && (
        <div>
          <div className={styles.label}>Evidence</div>
          <ul style={{ fontSize: '0.85rem', margin: '0.25rem 0' }}>
            {edit.evidence_fact_ids.map(id => (
              <li key={id}>{id}</li>
            ))}
          </ul>
        </div>
      )}

      {edit.job_requirement_ids.length > 0 && (
        <div>
          <div className={styles.label}>Job Requirements</div>
          <ul style={{ fontSize: '0.85rem', margin: '0.25rem 0' }}>
            {edit.job_requirement_ids.map(id => (
              <li key={id}>{id}</li>
            ))}
          </ul>
        </div>
      )}

      <div className={styles.metrics}>
        <span>+{edit.score_contribution.toFixed(2)} points</span>
        <span>Cost: {edit.edit_cost.toFixed(2)}</span>
      </div>

      {isNeedsConfirmation && (
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.confirmBtn}
            onClick={() => confirmMutation.mutate()}
            disabled={isActing}
            aria-label="Confirm"
          >
            Confirm
          </button>
          <button
            type="button"
            className={styles.rejectBtn}
            onClick={() => rejectMutation.mutate()}
            disabled={isActing}
            aria-label="Reject"
          >
            Reject
          </button>
        </div>
      )}
    </div>
  )
}
