import { rm, mkdir } from 'node:fs/promises';
import path from 'node:path';
import { loadSiteData } from '../src/lib/data';
const output = path.resolve('public/evidence');
await rm(output, { recursive: true, force: true }); await mkdir(output, { recursive: true });
const data = await loadSiteData({ copyRoot: output });
console.log(`Prepared ${data.runs.length} runs and ${data.runs.reduce((n, r) => n + r.artifacts.length, 0)} allowlisted committed evidence files (${data.warnings.length} visible warnings).`);
