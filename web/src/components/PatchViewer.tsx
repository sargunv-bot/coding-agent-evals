import { PatchDiff } from '@pierre/diffs/react';

interface Props { patch: string; rawUrl?: string }

/** PatchDiff intentionally accepts one file per component. Keep mail headers with the first file. */
export function splitPatchByFile(patch: string): string[] {
  const starts = [...patch.matchAll(/^diff --git /gm)].map((match) => match.index);
  if (starts.length <= 1) return patch.trim() ? [patch] : [];
  return starts.map((start, index) => {
    const prefix = index === 0 && start > 0 ? patch.slice(0, start) : '';
    const end = starts[index + 1] ?? patch.length;
    return prefix + patch.slice(start, end);
  });
}

export function patchFileSummary(filePatch: string) {
  const header = filePatch.match(/^diff --git a\/(.+?) b\/(.+)$/m);
  const name = header?.[2] || header?.[1] || 'Patch';
  const lines = filePatch.split('\n');
  const additions = lines.filter((line) => line.startsWith('+') && !line.startsWith('+++')).length;
  const deletions = lines.filter((line) => line.startsWith('-') && !line.startsWith('---')).length;
  return { name, additions, deletions };
}

export function PatchViewer({ patch, rawUrl }: Props) {
  const files = splitPatchByFile(patch).map((filePatch) => ({ patch: filePatch, ...patchFileSummary(filePatch) }));
  return <section className="diff-shell" aria-labelledby="candidate-patch-heading">
    <div className="mb-3 flex flex-wrap items-center justify-between gap-2"><div><h2 id="candidate-patch-heading" className="text-xl font-bold">Candidate patch</h2><p className="text-sm opacity-70">{files.length} changed {files.length === 1 ? 'file' : 'files'} · expand a file to review it</p></div>{rawUrl && <a className="btn btn-sm btn-outline" href={rawUrl} download>Download raw patch</a>}</div>

    <p className="sr-only">Diff follows. Added and removed lines are distinguished by symbols, line numbers, and color.</p>
    {files.length > 0 ? <div className="mt-4 space-y-3">{files.map((file, index) =>
      <details className="evidence-file" key={file.name + index} open={files.length === 1 && patch.length < 8_000}>
        <summary><span className="file-name">{file.name}</span><span className="diff-counts"><span className="text-success">+{file.additions}</span> <span className="text-error">−{file.deletions}</span></span></summary>
        <div className="diff-viewport"><PatchDiff patch={file.patch} disableWorkerPool /></div>
      </details>)}
    </div> : <p className="alert mt-4">The candidate produced an empty patch.</p>}
  </section>;
}
