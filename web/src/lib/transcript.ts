import type { TranscriptEvent } from './types';
const MAX_EVENTS = 500;
const text = (v: unknown) => typeof v === 'string' ? v : undefined;
export function parseTranscript(source: string): { events: TranscriptEvent[]; warnings: string[]; truncated: boolean } {
  const warnings: string[] = []; const events: TranscriptEvent[] = [];
  const lines = source.split(/\r?\n/).filter(Boolean);
  for (let i = 0; i < Math.min(lines.length, MAX_EVENTS); i++) {
    try {
      const raw = JSON.parse(lines[i]); const part = raw?.part || {}; const state = part?.state || {}; const time = part?.time || {};
      events.push({ type: text(raw?.type) || text(part?.type) || 'unknown', timestamp: raw?.timestamp,
        text: text(part?.text) || text(raw?.text), tool: text(part?.tool), status: text(state?.status),
        input: state?.input, output: state?.output, error: state?.error, usage: part?.tokens || raw?.usage,
        elapsedMs: typeof time.start === 'number' && typeof time.end === 'number' ? time.end - time.start : undefined, raw });
    } catch { warnings.push(`Line ${i + 1} is not valid JSON and was skipped.`); }
  }
  return { events, warnings, truncated: lines.length > MAX_EVENTS };
}
