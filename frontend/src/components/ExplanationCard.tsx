import { useMutation } from '@tanstack/react-query'
import { updateEditStatus } from '../api/recourse'
import type { ExplanationCardResponse } from '../types/recourse'
import styles from './ExplanationCard.module.css'

interface Props {
  edit: ExplanationCardResponse
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
    mutationFn: () => updateEditStatus(edit.edit_id, 'confirm'),
    onSuccess: () => onConfirm(edit.edit_id),
  })

  const rejectMutation = useMutation({
    mutationFn: () => updateEditStatus(edit.edit_id, 'reject'),
    onSuccess: () => onReject(edit.edit_id),
  })

  const isActing = confirmMutation.isPending || rejectMutation.isPending

  // Zip evidence_fact_ids with evidence_claim_texts for human-readable display
  const evidenceItems = edit.evidence_fact_ids.map((id, i) => ({
    id,
    text: edit.evidence_claim_texts[i] ?? id,
  }))

  // Zip job_requirement_ids with requirement_texts
  const requirementItems = edit.job_requirement_ids.map((id, i) => ({
    id,
    text: edit.requirement_texts[i] ?? id,
  }))

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

      {/* Field 1: prose_description */}
      <p>{edit.prose_description}</p>

      <p style={{ color: '#6b7280', fontSize: '0.85rem' }}>
        <em>Original:</em> {edit.original_text}
      </p>
      <p style={{ color: '#374151', fontSize: '0.85rem' }}>
        <em>Proposed:</em> {edit.proposed_text}
      </p>

      {/* Field 2: ats_improvement_reason */}
      <div className={styles.label}>Why this helps</div>
      <p style={{ fontSize: '0.9rem' }}>{edit.ats_improvement_reason}</p>

      {/* Field 3: evidence with human-readable claim texts */}
      {evidenceItems.length > 0 && (
        <div>
          <div className={styles.label}>Evidence</div>
          <ul style={{ fontSize: '0.85rem', margin: '0.25rem 0' }}>
            {evidenceItems.map(item => (
              <li key={item.id}>{item.text}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Field 4: job requirements with human-readable texts */}
      {requirementItems.length > 0 && (
        <div>
          <div className={styles.label}>Job Requirements</div>
          <ul style={{ fontSize: '0.85rem', margin: '0.25rem 0' }}>
            {requirementItems.map(item => (
              <li key={item.id}>{item.text}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Fields 5 & 6: score_contribution and edit_cost */}
      <div className={styles.metrics}>
        <span>+{edit.score_contribution.toFixed(2)} points</span>
        <span>Cost: {edit.edit_cost.toFixed(2)}</span>
      </div>

      {/* Field 7: verification_status badge already shown above */}

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
