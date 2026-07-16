import type { ReviewState } from './types';
export function reviewState(state: string, review?: Record<string, unknown>): ReviewState {
  if (review && Object.keys(review).length) return {
    kind: 'reviewed', label: 'Reviewed', review,
    explanation: 'Model-blind subjective review is shown separately and cannot override deterministic verification.',
  };
  if (state === 'completed') return {
    kind: 'pending', label: 'Pending model-blind review',
    explanation: 'Queued after the run. Deterministic verification remains authoritative.',
  };
  return { kind: 'not-ready', label: 'Not ready', explanation: 'This partial cell is not ready for subjective review.' };
}
