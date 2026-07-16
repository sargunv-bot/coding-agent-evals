import { mkdtemp, mkdir, writeFile, symlink } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import os from 'node:os'; import path from 'node:path';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { loadSiteData } from '../src/lib/data';
import { humanizeEnum, modelSlug } from '../src/lib/format';
import { reviewState } from '../src/lib/review';
import { containedFile, safeRelativePath, validateHttpUrl } from '../src/lib/safety';
import { parseTranscript } from '../src/lib/transcript';
import { summarizeTranscript, TranscriptViewer } from '../src/components/TranscriptViewer';
import { patchFileSummary, splitPatchByFile } from '../src/components/PatchViewer';

async function fixture() {
  const root = await mkdtemp(path.join(os.tmpdir(), 'eval-site-'));
  await mkdir(path.join(root, 'tasks/t-1'), { recursive: true }); await mkdir(path.join(root, 'experiments'), { recursive: true }); await mkdir(path.join(root, 'reports/experiments/e-1/evidence/runs/p__m__t-1__default__ask_user__r01'), { recursive: true });
  await writeFile(path.join(root, 'tasks/t-1/task.toml'), `[task]\ndescription="A task"\n[metadata]\ntask_id="t-1"\ndisplay_title="Task one"\nrepository_url="https://example.com/repo"\nbase_commit_hash="abc"\ngold_commit_hash="def"\nupstream_primary_pr_url="https://example.com/repo/pull/1"\n`);
  await writeFile(path.join(root, 'experiments/e-1.toml'), `[experiment]\nid="e-1"\nrepeats=1\n[[models]]\nprovider="p"\nmodel="m"\n[[cells]]\ntask="t-1"\nmode="ask_user"\n`);
  await writeFile(path.join(root, 'reports/experiments/e-1/results.json'), JSON.stringify({ rows: [{ cell_id:'p__m__t-1__default__ask_user__r01', task_id:'t-1', provider:'p', model:'m', mode:'ask_user', repeat:1, state:'completed', deterministic_pass:true }] }));
  execFileSync('git', ['init','-q'], { cwd: root }); execFileSync('git', ['add','.'], { cwd: root }); return root;
}

describe('labels and review semantics', () => {
  it('humanizes enums and stable model slugs', () => { expect(humanizeEnum('ask_user')).toBe('Ask user'); expect(humanizeEnum('validation-fail-fast')).toBe('Validation fail-fast'); expect(modelSlug('OpenCode Go','Kimi/K2')).toBe('opencode-go--kimi-k2'); });
  it('uses pending, not-ready, and reviewed states without overriding verification', () => { expect(reviewState('completed').kind).toBe('pending'); expect(reviewState('partial').label).toBe('Not ready'); const state=reviewState('completed',{score:5}); expect(state.kind).toBe('reviewed'); expect(state.explanation).toContain('cannot override'); });
});
describe('path and provenance safety', () => {
  it('rejects traversal, absolute, and non-HTTP links', () => { expect(() => safeRelativePath('../x')).toThrow(); expect(() => safeRelativePath('/x')).toThrow(); expect(() => validateHttpUrl('javascript:alert(1)','url')).toThrow(); });
  it('rejects symlink evidence even when the target is contained', async () => { const root=await mkdtemp(path.join(os.tmpdir(),'paths-')); await writeFile(path.join(root,'real'),'x'); await symlink(path.join(root,'real'),path.join(root,'link')); await expect(containedFile(root,'link')).rejects.toThrow(/non-symlink/); });
  it('groups task/model/run data and preserves validated provenance links', async () => { const root=await fixture(); const data=await loadSiteData({dataRoot:root}); expect(data.tasks[0].runs).toHaveLength(1); expect(data.models[0].key).toBe('p/m'); expect(data.tasks[0].upstreamPrimaryUrl).toBe('https://example.com/repo/pull/1'); expect(data.experiments[0].plannedCells).toBe(1); });
  it('keeps malformed optional input visible as a warning', async () => { const root=await fixture(); await writeFile(path.join(root,'reports/experiments/e-1/results.json'),'{bad'); const data=await loadSiteData({dataRoot:root}); expect(data.warnings.some((w) => w.message.includes('results.json'))).toBe(true); });
});
describe('transcript parsing and XSS', () => {
  it('parses tool statuses, reasoning, usage, unknown events, and malformed lines', () => { const parsed=parseTranscript([JSON.stringify({type:'reasoning',part:{text:'why'}}),JSON.stringify({type:'tool_use',part:{tool:'bash',state:{status:'error',input:{x:1},error:'bad'}}}),JSON.stringify({type:'step_finish',part:{tokens:{total:2}}}),JSON.stringify({type:'new_kind',payload:1}),'bad'].join('\n')); expect(parsed.events.map((e) => e.type)).toEqual(['reasoning','tool_use','step_finish','new_kind']); expect(parsed.warnings).toHaveLength(1); });
  it('escapes transcript content instead of injecting HTML', () => { const source='<script>alert(1)</script>'; const {events}=parseTranscript(JSON.stringify({type:'text',part:{text:source}})); const html=renderToStaticMarkup(<TranscriptViewer events={events} truncated={false} warnings={[]}/>); expect(html).not.toContain(source); expect(html).toContain('&lt;script&gt;'); });
  it('keeps final answers and clarifications visible while grouping work by step', () => {
    const events = parseTranscript([
      JSON.stringify({type:'step_start'}),
      JSON.stringify({type:'tool_use',part:{tool:'proctor_ask_user',state:{status:'completed'}}}),
      JSON.stringify({type:'step_finish'}),
      JSON.stringify({type:'text',part:{text:'Done'}}),
    ].join('\n')).events;
    const summary = summarizeTranscript(events);
    expect(summary.steps).toHaveLength(2);
    expect(summary.clarifications).toHaveLength(1);
    expect(summary.finalMessages[0].text).toBe('Done');
  });
});
describe('diff rendering', () => {
  it('splits multi-file git patches for Pierre PatchDiff', () => {
    const patch = 'diff --git a/one b/one\n--- a/one\n+++ b/one\n@@ -1 +1 @@\n-a\n+b\n' +
      'diff --git a/two b/two\n--- a/two\n+++ b/two\n@@ -1 +1 @@\n-c\n+d\n';
    const files = splitPatchByFile(patch);
    expect(files).toHaveLength(2);
    expect(files[0]).toContain('a/one');
    expect(files[0]).not.toContain('a/two');
    expect(files[1]).toContain('a/two');
    expect(patchFileSummary(files[0])).toMatchObject({ name: 'one', additions: 1, deletions: 1 });
  });
});
