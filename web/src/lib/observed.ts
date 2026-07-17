import type { ObservedCheck, ObservedChecks } from './types';

// Verifier logs may contain ANSI SGR escapes.
// eslint-disable-next-line no-control-regex
const clean = (source: string) => source.replace(/\x1b\[[0-9;]*m/g, '').trim();

export function extractObservedChecks(taskId: string, source = '', verifierPassed?: boolean): ObservedChecks {
  const output = clean(source);
  const checks: ObservedCheck[] = [];
  let reportedTotal = 0;
  let reportedFailed = 0;
  let compilerErrors = 0;
  let phase: string | undefined;

  const add = (name: string, status: ObservedCheck['status'], detail?: string) => {
    if (!checks.some((check) => check.name === name && check.status === status)) checks.push({ name, status, detail });
  };

  if (taskId.startsWith('ce-01')) {
    for (const line of output.split('\n')) {
      const match = line.match(/^\s*(PASS|FAIL)[:\s-]+(.+)$/i);
      if (match) add(match[2].trim(), match[1].toLowerCase() as 'pass' | 'fail');
    }
    phase = 'Behavior checks';
  } else if (taskId.startsWith('ce-02')) {
    for (const line of output.split('\n')) {
      const match = line.match(/^---\s+(PASS|FAIL):\s+([^\s(]+)/);
      if (match) add(match[2], match[1].toLowerCase() as 'pass' | 'fail');
    }
    for (const match of output.matchAll(/^FAIL\s+([^\s]+)(?:\s+[\d.]+s)?$/gm)) add(match[1], 'fail');
    phase = 'Go tests';
  } else if (taskId.startsWith('ce-03')) {
    for (const match of output.matchAll(/^test\s+(.+?)\s+\.\.\.\s+(ok|FAILED)$/gm)) add(match[1], match[2] === 'ok' ? 'pass' : 'fail');
    for (const match of output.matchAll(/test result: \w+\. (\d+) passed; (\d+) failed/g)) {
      reportedTotal += Number(match[1]) + Number(match[2]);
      reportedFailed += Number(match[2]);
    }
    phase = output.includes('Compiling') ? 'Rust tests' : 'Verifier';
  } else if (taskId.startsWith('ce-04')) {
    phase = output.includes('runtime') ? 'Runtime' : /compil/i.test(output) ? 'Compilation' : 'Structure';
    for (const line of output.split('\n')) {
      const match = line.match(/^\s*(PASS|FAIL)[:\s-]+(.+)$/i);
      if (match) add(match[2], match[1].toLowerCase() as 'pass' | 'fail');
    }
  } else if (taskId.startsWith('ce-05')) {
    const rustSummaries = Array.from(output.matchAll(/due to (\d+) previous errors?/g));
    const rustSummary = rustSummaries[rustSummaries.length - 1];
    compilerErrors = rustSummary ? Number(rustSummary[1]) : (output.match(/^error(?:\[E\d+\])?:/gm) || []).length;
    phase = compilerErrors ? 'Compilation' : 'Rust tests';
    for (const match of output.matchAll(/^test\s+(.+?)\s+\.\.\.\s+(ok|FAILED)$/gm)) add(match[1], match[2] === 'ok' ? 'pass' : 'fail');
  } else if (taskId.startsWith('ce-06')) {
    phase = 'Structural assertions';
    for (const line of output.split('\n')) {
      const match = line.match(/^\s*(PASS|FAIL|OK)[:\s-]+(.+)$/i);
      if (match) add(match[2], match[1].toUpperCase() === 'FAIL' ? 'fail' : 'pass');
    }
    if (!checks.length && verifierPassed === true) add('Workflow structure verification', 'pass');
  } else if (taskId.startsWith('ce-07')) {
    compilerErrors = (output.match(/^e: .*$/gm) || []).length;
    for (const match of output.matchAll(/(\d+) tests completed, (\d+) failed/g)) {
      reportedTotal += Number(match[1]);
      reportedFailed += Number(match[2]);
    }
    for (const match of output.matchAll(/^([^\n]+) > ([^\n]+) FAILED$/gm)) add(`${match[1]} › ${match[2]}`, 'fail');
    const abiFailure = /(?:checkKotlinAbi FAILED|ABI (?:has changed|check failed)|Legacy ABI check failed)/i.test(output);
    if (abiFailure) add('Kotlin/JVM ABI compatibility', 'fail', 'Generated ABI differs from the committed declarations.');
    phase = compilerErrors ? 'Kotlin compilation' : abiFailure ? 'ABI compatibility' : output.includes('Test') ? 'Gradle tests' : 'Gradle build';
  }

  const namedPassed = checks.filter((check) => check.status === 'pass').length;
  const namedFailed = checks.filter((check) => check.status === 'fail' || check.status === 'error').length;
  if (!reportedTotal && !compilerErrors && !taskId.startsWith('ce-07')) {
    reportedTotal = namedPassed + namedFailed;
    reportedFailed = namedFailed;
  }
  const abiFailed = checks.some((check) => check.name === 'Kotlin/JVM ABI compatibility' && check.status === 'fail');

  let summary: string;
  if (compilerErrors) summary = `Compilation failed · ${compilerErrors} ${compilerErrors === 1 ? 'error' : 'errors'}`;
  else if (abiFailed && reportedTotal) summary = `${reportedTotal - reportedFailed}/${reportedTotal} observed tests · ABI compatibility failed`;
  else if (abiFailed) summary = 'ABI compatibility failed';
  else if (reportedTotal) summary = `${reportedTotal - reportedFailed}/${reportedTotal} observed tests${reportedFailed ? ` · ${reportedFailed} failed` : ''}`;
  else if (checks.length) summary = namedFailed ? `${namedFailed} named ${namedFailed === 1 ? 'check' : 'checks'} failed` : `${namedPassed} named ${namedPassed === 1 ? 'check' : 'checks'} passed`;
  else summary = verifierPassed === true ? 'Verifier completed successfully' : verifierPassed === false ? `${phase || 'Verifier'} failed · no named check totals observed` : 'No structured check result observed';

  return {
    summary,
    phase,
    passed: reportedTotal ? reportedTotal - reportedFailed : namedPassed || undefined,
    failed: reportedTotal ? reportedFailed || undefined : namedFailed || undefined,
    total: reportedTotal || undefined,
    compilerErrors: compilerErrors || undefined,
    checks,
  };
}
