import type { ReviewPolicy, ReviewState } from './types';
export function reviewState(state: string, review?: Record<string, unknown>, policy: ReviewPolicy = 'required'): ReviewState {
  if (review && Object.keys(review).length) return {
    kind: 'reviewed', label: 'Reviewed', review,
    explanation: 'Model-blind subjective review is shown separately and cannot override deterministic verification.',
  };
  if (state !== 'completed') return { kind: 'not-ready', label: 'Not ready', explanation: 'This partial cell is not ready for subjective review.' };
  if (policy === 'withheld') return {
    kind: 'withheld', label: 'Review withheld pending validity audit',
    explanation: 'Qualitative review is withheld until task and verifier validity is resolved. Deterministic output is retained but should not be used comparatively.',
  };
  if (policy === 'disabled') return {
    kind: 'not-applicable', label: 'Qualitative review not requested',
    explanation: 'This experiment does not include model-blind qualitative review.',
  };
  return {
    kind: 'pending', label: 'Pending model-blind review',
    explanation: 'Queued after the run. Deterministic verification remains authoritative.',
  };
}
