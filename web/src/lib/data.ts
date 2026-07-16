import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { copyFile, mkdir, readFile, readdir, realpath } from 'node:fs/promises';
import path from 'node:path';
import { parse as parseToml } from 'smol-toml';
import { basePath, modelSlug } from './format';
import { reviewState } from './review';
import { containedFile, safeRelativePath, validateHttpUrl } from './safety';
import { parseTranscript } from './transcript';
import type { Artifact, Experiment, Model, Run, SiteData, Task, TaskMetadata, Warning } from './types';

const ALLOWED_ARTIFACTS = new Set(['instruction.txt','matrix-record.json','model.patch','opencode.json','transcript.jsonl','verifier/stdout.txt','proctor-review.json','artifacts.json']);
const utf8 = async (file: string) => readFile(file, 'utf8');
const sha256 = (data: Buffer) => createHash('sha256').update(data).digest('hex');
const asRecord = (v: unknown): Record<string, any> => v && typeof v === 'object' && !Array.isArray(v) ? v as Record<string, any> : {};

async function optionalJson(file: string, warnings: Warning[], scope: string): Promise<any> {
  try { return JSON.parse(await utf8(file)); }
  catch (error: any) { if (error?.code !== 'ENOENT') warnings.push({ scope, message: `${path.basename(file)}: ${error.message}` }); return undefined; }
}
async function optionalToml(file: string, warnings: Warning[], scope: string): Promise<any> {
  try { return parseToml(await utf8(file)); }
  catch (error: any) { if (error?.code !== 'ENOENT') warnings.push({ scope, message: `${path.basename(file)}: ${error.message}` }); return undefined; }
}
async function dirs(file: string): Promise<string[]> {
  try { return (await readdir(file, { withFileTypes: true })).filter((d) => d.isDirectory() && !d.isSymbolicLink()).map((d) => d.name).sort(); }
  catch { return []; }
}
function trackedSet(root: string, warnings: Warning[]): Set<string> {
  try { return new Set(execFileSync('git', ['-C', root, 'ls-files', '-z'], { encoding: 'utf8' }).split('\0').filter(Boolean)); }
  catch { warnings.push({ scope: 'evidence', message: 'Data root is not a Git checkout; evidence downloads were not published because committed status could not be proven.' }); return new Set(); }
}
function rowIdentity(cellId: string): Partial<Run> {
  const parts = cellId.split('__');
  return parts.length >= 6 ? { provider: parts[0], model: parts[1], taskId: parts[2], scenario: parts[3] === 'default' ? '' : parts[3], mode: parts[4], repeat: Number(parts[5].replace(/^r/, '')) || 1 } : {};
}
function metadataFromToml(doc: any, warnings: Warning[]): TaskMetadata | undefined {
  const m = asRecord(doc?.metadata); const t = asRecord(doc?.task); if (!m.task_id) return undefined;
  const url = (key: string) => { try { return validateHttpUrl(m[key], key); } catch (e: any) { warnings.push({ scope: String(m.task_id), message: e.message }); return undefined; } };
  return { taskId: String(m.task_id), title: String(m.display_title || m.task_id), description: String(t.description || ''), category: m.category, language: m.language,
    repositoryUrl: url('repository_url'), baseCommitHash: m.base_commit_hash, goldCommitHash: m.gold_commit_hash,
    upstreamPrimaryUrl: url('upstream_primary_pr_url'), upstreamBroaderContextUrl: url('upstream_broader_context_pr_url'), upstreamOriginalDiscussionUrl: url('upstream_original_discussion_url') };
}

export interface LoadOptions { dataRoot?: string; taskRoot?: string; copyRoot?: string }
export async function loadSiteData(options: LoadOptions = {}): Promise<SiteData> {
  const dataRoot = await realpath(options.dataRoot || process.env.RESULTS_DATA_ROOT || path.resolve(process.cwd(), '..'));
  const taskRoot = await realpath(options.taskRoot || process.env.TASK_DATA_ROOT || dataRoot);
  const warnings: Warning[] = []; const tracked = trackedSet(dataRoot, warnings);
  const taskMap = new Map<string, TaskMetadata>();
  for (const id of await dirs(path.join(taskRoot, 'tasks'))) {
    const local: Warning[] = []; const meta = metadataFromToml(await optionalToml(path.join(taskRoot, 'tasks', id, 'task.toml'), local, id), local);
    warnings.push(...local); if (meta) taskMap.set(meta.taskId, meta);
  }
  const experiments: Experiment[] = []; const allRuns: Run[] = [];
  const reportsRoot = path.join(dataRoot, 'reports', 'experiments');
  for (const experimentId of await dirs(reportsRoot)) {
    const ew: Warning[] = []; const reportDir = path.join(reportsRoot, experimentId);
    const manifest = await optionalToml(path.join(dataRoot, 'experiments', `${experimentId}.toml`), ew, experimentId);
    const resultDoc = await optionalJson(path.join(reportDir, 'results.json'), ew, experimentId);
    const rows = Array.isArray(resultDoc?.rows) ? resultDoc.rows : [];
    const byCell = new Map<string, any>(rows.filter((r: any) => typeof r?.cell_id === 'string').map((r: any) => [r.cell_id, r]));
    const runRoot = path.join(reportDir, 'evidence', 'runs');
    for (const cellId of await dirs(runRoot)) if (!byCell.has(cellId)) byCell.set(cellId, { cell_id: cellId, state: 'partial' });
    const runs: Run[] = [];
    for (const [cellId, sourceRow] of [...byCell.entries()].sort(([a],[b]) => a.localeCompare(b))) {
      const rw: Warning[] = []; const runDir = path.join(runRoot, cellId);
      const matrix = await optionalJson(path.join(runDir, 'matrix-record.json'), rw, cellId); const cell = asRecord(matrix?.cell); const attempts = Array.isArray(matrix?.attempts) ? matrix.attempts : [];
      const latest = asRecord(attempts.at(-1)?.result); const row = { ...rowIdentity(cellId), ...cell, ...latest, ...sourceRow };
      const state = String(sourceRow.state || matrix?.state || (attempts.length ? 'completed' : 'partial'));
      const artifactManifest = await optionalJson(path.join(runDir, 'artifacts.json'), rw, cellId);
      const entries = Array.isArray(artifactManifest) ? artifactManifest : [];
      const artifacts: Artifact[] = [];
      for (const item of entries) {
        try {
          const rel = safeRelativePath(String(item?.path || '')); if (!ALLOWED_ARTIFACTS.has(rel)) throw new Error(`Artifact is not allowlisted: ${rel}`);
          const repoRel = path.relative(dataRoot, path.join(runDir, rel)).split(path.sep).join('/');
          if (!tracked.has(repoRel)) throw new Error(`Artifact is not committed: ${rel}`);
          const file = await containedFile(runDir, rel); const data = await readFile(file); const actual = sha256(data);
          const url = basePath(`evidence/${encodeURIComponent(experimentId)}/${encodeURIComponent(cellId)}/${rel.split('/').map(encodeURIComponent).join('/')}`);
          artifacts.push({ path: rel, url, bytes: data.length, sha256: actual, expectedSha256: item.sha256, hashMatches: !item.sha256 || item.sha256 === actual });
          if (item.sha256 && item.sha256 !== actual) rw.push({ scope: cellId, message: `Hash mismatch for ${rel}; published hash was recomputed.` });
          if (options.copyRoot) { const target = path.join(options.copyRoot, experimentId, cellId, rel); await mkdir(path.dirname(target), { recursive: true }); await copyFile(file, target); }
        } catch (e: any) { rw.push({ scope: cellId, message: e.message }); }
      }
      const review = await optionalJson(path.join(runDir, 'proctor-review.json'), rw, cellId);
      const patchArtifact = artifacts.find((a) => a.path === 'model.patch'); const transcriptArtifact = artifacts.find((a) => a.path === 'transcript.jsonl');
      let patch: string | undefined; let transcriptSource = '';
      try { if (patchArtifact) patch = await utf8(await containedFile(runDir, patchArtifact.path)); } catch (e: any) { rw.push({ scope: cellId, message: e.message }); }
      try { if (transcriptArtifact) transcriptSource = await utf8(await containedFile(runDir, transcriptArtifact.path)); } catch (e: any) { rw.push({ scope: cellId, message: e.message }); }
      const parsed = parseTranscript(transcriptSource);
      let verifierOutput: string | undefined; try { if (artifacts.some((a) => a.path === 'verifier/stdout.txt')) verifierOutput = await utf8(await containedFile(runDir, 'verifier/stdout.txt')); } catch (e: any) { rw.push({ scope: cellId, message: e.message }); }
      const usage = asRecord(latest.usage); const verification = asRecord(latest.verification);
      const run: Run = { experimentId, cellId, taskId: String(row.task_id || 'unknown-task'), provider: String(row.provider || 'unknown-provider'), model: String(row.model || 'unknown-model'), mode: String(row.mode || row.instruction_mode || 'baseline'),
        scenario: String(row.scenario || ''), repeat: Number(row.repeat || 1), runId: row.run_id ? String(row.run_id) : undefined, state, completionStatus: row.agent_completion_status,
        deterministicPass: typeof row.deterministic_pass === 'boolean' ? row.deterministic_pass : typeof verification.expectation_met === 'boolean' ? verification.expectation_met : undefined,
        verificationOutcome: row.verification_outcome || verification.outcome, infrastructureError: state === 'infrastructure_error' || attempts.at(-1)?.kind === 'infrastructure_error', durationSeconds: Number(row.duration_seconds || latest.duration_seconds) || undefined,
        tokens: { input: Number(row.input_tokens ?? usage.input_tokens) || 0, cachedInput: Number(row.cached_input_tokens ?? usage.cached_input_tokens) || 0, output: Number(row.output_tokens ?? usage.output_tokens) || 0, reasoning: Number(row.reasoning_tokens ?? usage.reasoning_tokens) || 0 },
        artifacts, patch, transcript: parsed.events, transcriptTruncated: parsed.truncated, transcriptWarnings: parsed.warnings, verifierOutput, reviewState: reviewState(state, asRecord(review)), warnings: rw };
      runs.push(run); allRuns.push(run); ew.push(...rw);
    }
    const exp = asRecord(manifest?.experiment); const plannedCells = (Array.isArray(manifest?.models) ? manifest.models.length : 0) * (Array.isArray(manifest?.cells) ? manifest.cells.length : 0) * Number(exp.repeats || 1);
    experiments.push({ id: experimentId, description: exp.description, stage: exp.stage, plannedCells, runs, warnings: ew }); warnings.push(...ew);
  }
  for (const run of allRuns) run.taskTitle = taskMap.get(run.taskId)?.title || run.taskId;
  allRuns.sort((a,b) => a.taskId.localeCompare(b.taskId) || a.provider.localeCompare(b.provider) || a.model.localeCompare(b.model) || a.cellId.localeCompare(b.cellId));
  const tasks: Task[] = [...new Set([...taskMap.keys(), ...allRuns.map((r) => r.taskId)])].sort().map((taskId) => { const meta = taskMap.get(taskId) || { taskId, title: taskId, description: 'Task metadata is not available.' }; const runs = allRuns.filter((r) => r.taskId === taskId); return { ...meta, runs, scenarios: [...new Set(runs.map((r) => r.scenario).filter(Boolean))].sort() }; });
  const modelMap = new Map<string, Model>(); for (const run of allRuns) { const key = `${run.provider}/${run.model}`; const model = modelMap.get(key) || { key, slug: modelSlug(run.provider, run.model), provider: run.provider, name: run.model, runs: [] }; model.runs.push(run); modelMap.set(key, model); }
  return { tasks, models: [...modelMap.values()].sort((a,b) => a.key.localeCompare(b.key)), experiments, runs: allRuns, warnings };
}
