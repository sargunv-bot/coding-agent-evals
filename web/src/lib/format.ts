const ENUM_LABELS: Record<string, string> = {
  ask_user: 'Ask user', full_info: 'Full info', baseline: 'Baseline', completed: 'Completed',
  infrastructure_error: 'Infrastructure error', not_started: 'Not started', in_progress: 'In progress',
  default: 'Default', validation_fail_fast: 'Validation fail-fast', all_errors_as_result: 'All errors as result',
  'validation-fail-fast': 'Validation fail-fast', 'all-errors-as-result': 'All errors as result',
};
export function humanizeEnum(value: string | null | undefined): string {
  if (!value) return 'Default';
  return ENUM_LABELS[value] || value.replace(/[_-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}
export function modelSlug(provider: string, model: string): string {
  return `${provider}--${model}`.toLowerCase().replace(/[^a-z0-9.-]+/g, '-').replace(/^-|-$/g, '');
}
export function basePath(path = ''): string {
  const base = (import.meta.env?.BASE_URL || process.env.BASE_PATH || '/coding-agent-evals/').replace(/\/?$/, '/');
  return `${base}${path.replace(/^\//, '')}`;
}
export function runHref(run: { experimentId: string; cellId: string }): string {
  return basePath(`runs/${encodeURIComponent(run.experimentId)}/${encodeURIComponent(run.cellId)}/`);
}
export const number = (value: number | undefined) => new Intl.NumberFormat('en-US').format(value || 0);
export function duration(seconds: number | undefined): string {
  if (seconds === undefined) return '—';
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  return `${minutes}m ${remainder}s`;
}
