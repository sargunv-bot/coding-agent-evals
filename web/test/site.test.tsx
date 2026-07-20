import { mkdtemp, mkdir, writeFile, symlink } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import os from 'node:os'; import path from 'node:path';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { loadSiteData } from '../src/lib/data';
import { duration, humanizeEnum, modelSlug } from '../src/lib/format';
import { reviewState } from '../src/lib/review';
import { containedFile, safeRelativePath, validateHttpUrl } from '../src/lib/safety';
import { parseTranscript } from '../src/lib/transcript';
import { groupTranscriptSteps, summarizeTranscript, TranscriptViewer } from '../src/components/TranscriptViewer';
import { PatchViewer, patchFileSummary, splitPatchByFile } from '../src/components/PatchViewer';
import { extractObservedChecks } from '../src/lib/observed';

async function fixture() {
  const root = await mkdtemp(path.join(os.tmpdir(), 'eval-site-'));
  await mkdir(path.join(root, 'tasks/t-1'), { recursive: true }); await mkdir(path.join(root, 'experiments'), { recursive: true }); await mkdir(path.join(root, 'reports/experiments/e-1/evidence/runs/p__m__t-1__default__r01'), { recursive: true });
  await writeFile(path.join(root, 'tasks/t-1/task.toml'), `[task]\ndescription="A task"\n[metadata]\ntask_id="t-1"\ndisplay_title="Task one"\nrepository_url="https://example.com/repo"\nbase_commit_hash="abc"\ngold_commit_hash="def"\nupstream_primary_pr_url="https://example.com/repo/pull/1"\n`);
  await writeFile(path.join(root, 'experiments/e-1.toml'), `[experiment]\nid="e-1"\nrepeats=1\n[[models]]\nprovider="p"\nmodel="m"\n[[models]]\nprovider="p"\nmodel="m2"\n[[cells]]\ntask="t-1"\n`);
  await writeFile(path.join(root, 'experiments/e-1-selection.json'), JSON.stringify({ execution_order: ['p__m__t-1__default__r01'] }));
  await writeFile(path.join(root, 'reports/experiments/e-1/results.json'), JSON.stringify({ rows: [{ cell_id:'p__m__t-1__default__r01', task_id:'t-1', provider:'p', model:'m', repeat:1, state:'completed', deterministic_pass:true }] }));
  execFileSync('git', ['init','-q'], { cwd: root }); execFileSync('git', ['add','.'], { cwd: root }); return root;
}

describe('labels and review semantics', () => {
  it('humanizes enums and stable model slugs', () => { expect(humanizeEnum('validation-fail-fast')).toBe('Validation fail-fast'); expect(modelSlug('OpenCode Go','Kimi/K2')).toBe('opencode-go--kimi-k2'); expect(duration(2564.3)).toBe('42m 44s'); });
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
  it('keeps final answers visible while grouping work by step', () => {
    const events = parseTranscript([
      JSON.stringify({type:'step_start'}),
      JSON.stringify({type:'step_finish'}),
      JSON.stringify({type:'text',part:{text:'Done'}}),
    ].join('\n')).events;
    const summary = summarizeTranscript(events);
    expect(summary.steps).toHaveLength(1);
    expect(summary.finalMessages[0].text).toBe('Done');
  });
  it('groups reasoning, tools, and usage into one canonical agent step', () => {
    const events = parseTranscript([
      JSON.stringify({type:'step_start',timestamp:1000}),
      JSON.stringify({type:'reasoning',timestamp:1100,part:{text:'Inspect first'}}),
      JSON.stringify({type:'tool_use',timestamp:1200,part:{tool:'read',state:{status:'completed',input:{path:'x'},output:'ok'}}}),
      JSON.stringify({type:'step_finish',timestamp:1500,part:{tokens:{input:100,output:20,cache:{read:40}}}}),
    ].join('\n')).events;
    const steps = groupTranscriptSteps(events);
    expect(steps).toHaveLength(1);
    expect(steps[0].reasoning).toHaveLength(1);
    expect(steps[0].tools).toHaveLength(1);
    expect(steps[0].finish?.usage).toMatchObject({ input: 100, output: 20 });
    expect(steps[0].durationMs).toBe(500);
  });
});
describe('task-specific observed verifier summaries', () => {
  it.each([
    ['ce-01-antidote-output', 'PASS: stdout isolated\nFAIL: diagnostic preserved', '1/2 observed tests · 1 failed'],
    ['ce-02-horologia-overdue', '--- PASS: TestDue\n--- FAIL: TestOverdue', '1/2 observed tests · 1 failed'],
    ['ce-03-jvl-completions', 'running 2 tests\ntest composed ... ok\ntest nested ... FAILED\ntest result: FAILED. 1 passed; 1 failed', '1/2 observed tests · 1 failed'],
    ['ce-04-maplibre-source-location', 'PASS: structure\nFAIL: runtime', '1/2 observed tests · 1 failed'],
    ['ce-05-mise-slsa-archive', 'error[E0433]: missing\nerror[E0425]: absent', 'Compilation failed · 2 errors'],
    ['ce-06-maplibre-ffi-ci', 'PASS: workflow pins generated artifact', '1/1 observed tests'],
    ['ce-07-mobility-result', 'e: unresolved reference\ne: type inference failed', 'Compilation failed · 2 errors'],
  ])('extracts honest evidence for %s', (task, output, expected) => {
    expect(extractObservedChecks(task, output, false).summary).toBe(expected);
  });
  it('separates passing CE-07 behavior from a failing ABI check', () => {
    const observed = extractObservedChecks('ce-07-mobility-result', '3 tests completed, 0 failed\n> Task :gbfs-v1:checkKotlinAbi FAILED\nABI has changed', false);
    expect(observed.summary).toBe('3/3 observed tests · ABI compatibility failed');
    expect(observed.phase).toBe('ABI compatibility');
    expect(observed.checks).toContainEqual(expect.objectContaining({ name: 'Kotlin/JVM ABI compatibility', status: 'fail' }));
  });
  it('uses the Rust compiler summary instead of counting its trailing aggregate as another error', () => {
    expect(extractObservedChecks('ce-05-mise-slsa-archive', 'error[E1]: one\nerror[E2]: two\nerror: could not compile due to 12 previous errors', false).summary).toBe('Compilation failed · 12 errors');
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
  it('renders every file expanded without duplicating an outer path disclosure', () => {
    const patch = 'diff --git a/one b/one\n--- a/one\n+++ b/one\n@@ -1 +1 @@\n-a\n+b\n';
    const html = renderToStaticMarkup(<PatchViewer patch={patch}/>);
    expect(html).not.toContain('<details');
    expect(html).not.toContain('expand a file');
    expect(html).toContain('diff-viewport');
  });
});
