export interface Warning { scope: string; message: string }
export interface Artifact { path: string; url: string; bytes: number; sha256: string; expectedSha256?: string; hashMatches?: boolean }
export interface ReviewState { kind: 'pending' | 'not-ready' | 'reviewed'; label: string; explanation: string; review?: Record<string, unknown> }
export interface ObservedCheck { name: string; status: 'pass'|'fail'|'error'|'observed'; detail?: string }
export interface ObservedChecks { summary: string; phase?: string; passed?: number; failed?: number; total?: number; compilerErrors?: number; checks: ObservedCheck[] }
export interface TaskMetadata {
  taskId: string; title: string; description: string; category?: string; language?: string;
  repositoryUrl?: string; baseCommitHash?: string; goldCommitHash?: string;
  upstreamPrimaryUrl?: string; upstreamBroaderContextUrl?: string; upstreamOriginalDiscussionUrl?: string;
}
export interface TranscriptEvent { type: string; timestamp?: number; text?: string; tool?: string; status?: string; input?: unknown; output?: unknown; error?: unknown; usage?: any; elapsedMs?: number; raw: unknown }
export interface Run {
  experimentId: string; cellId: string; taskId: string; taskTitle?: string; provider: string; model: string;
  scenario: string; repeat: number; runId?: string; state: string; completionStatus?: string;
  deterministicPass?: boolean; verificationOutcome?: string;
  durationSeconds?: number; tokens: { input: number; cachedInput: number; output: number; reasoning: number };
  artifacts: Artifact[]; instruction?: string; patch?: string; transcript: TranscriptEvent[]; transcriptTruncated: boolean;
  transcriptWarnings: string[]; verifierOutput?: string; observed: ObservedChecks; reviewState: ReviewState; warnings: Warning[];
}
export interface Task extends TaskMetadata { runs: Run[]; scenarios: string[] }
export interface Model { key: string; slug: string; provider: string; name: string; runs: Run[] }
export interface Experiment { id: string; description?: string; stage?: string; plannedCells: number; runs: Run[]; warnings: Warning[] }
export interface SiteData { tasks: Task[]; models: Model[]; experiments: Experiment[]; runs: Run[]; warnings: Warning[] }
