import { useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Brain, CheckCircle2, ChevronDown, MessageSquare, Wrench, XCircle } from 'lucide-react';
import type { TranscriptEvent } from '../lib/types';

const json = (value: unknown) => typeof value === 'string' ? value : JSON.stringify(value, null, 2);
const isTool = (event: TranscriptEvent) => event.type === 'tool_use' || event.type === 'tool' || Boolean(event.tool);
const isReasoning = (event: TranscriptEvent) => event.type === 'reasoning' && Boolean(event.text?.trim());
const isMessage = (event: TranscriptEvent) => ['text', 'assistant', 'message'].includes(event.type) && Boolean(event.text?.trim());
const isStart = (event: TranscriptEvent) => event.type === 'step_start' || event.type === 'step-start';
const isFinish = (event: TranscriptEvent) => event.type === 'step_finish' || event.type === 'step-finish';
const hasError = (event: TranscriptEvent) => event.error !== undefined || event.status === 'error';
const relevant = (event: TranscriptEvent) => isTool(event) || isReasoning(event) || isMessage(event);
const compact = (value: number) => new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 }).format(value);

type Filter = 'all' | 'messages' | 'reasoning' | 'tools' | 'errors';

type TranscriptStep = {
  events: TranscriptEvent[];
  reasoning: TranscriptEvent[];
  tools: TranscriptEvent[];
  messages: TranscriptEvent[];
  finish?: TranscriptEvent;
  durationMs?: number;
};

function makeStep(events: TranscriptEvent[]): TranscriptStep {
  const timestamps = events.map((event) => event.timestamp).filter((value): value is number => typeof value === 'number');
  return {
    events,
    reasoning: events.filter(isReasoning),
    tools: events.filter(isTool),
    messages: events.filter(isMessage),
    finish: events.find(isFinish),
    durationMs: timestamps.length > 1 ? Math.max(...timestamps) - Math.min(...timestamps) : events.find((event) => event.elapsedMs !== undefined)?.elapsedMs,
  };
}

export function groupTranscriptSteps(events: TranscriptEvent[]): TranscriptStep[] {
  const groups: TranscriptEvent[][] = [];
  let current: TranscriptEvent[] = [];
  const flush = () => { if (current.some(relevant)) groups.push(current); current = []; };
  for (const event of events) {
    if (isStart(event)) { flush(); current = [event]; continue; }
    if (current.length) {
      current.push(event);
      if (isFinish(event)) flush();
    } else if (relevant(event)) groups.push([event]);
  }
  flush();
  return groups.map(makeStep);
}

export function summarizeTranscript(events: TranscriptEvent[]) {
  const finalMessages = events.filter(isMessage);
  return {
    finalMessages,
    steps: groupTranscriptSteps(events),
    toolCalls: events.filter(isTool).length,
  };
}

function stepMatches(step: TranscriptStep, filter: Filter) {
  if (filter === 'messages') return step.messages.length > 0;
  if (filter === 'reasoning') return step.reasoning.length > 0;
  if (filter === 'tools') return step.tools.length > 0;
  if (filter === 'errors') return step.events.some(hasError);
  return true;
}

function Step({ step, index, filter }: { step: TranscriptStep; index: number; filter: Filter }) {
  const errors = step.events.filter(hasError);
  const toolNames = [...new Set(step.tools.map((event) => event.tool || 'Tool'))];
  const preview = step.messages[0]?.text?.trim() || step.reasoning[0]?.text?.trim() || (errors[0]?.error ? `Error: ${json(errors[0].error)}` : '');
  const title = errors.length ? `${toolNames[0] || 'Step'} failed` : toolNames.length ? toolNames.slice(0, 3).join(' · ') : step.messages.length ? 'Assistant message' : 'Assistant reasoning';
  const usage = step.finish?.usage || {};
  const cache = usage.cache || {};
  const showMessages = filter === 'all' || filter === 'messages';
  const showReasoning = filter === 'all' || filter === 'reasoning';
  const showTools = filter === 'all' || filter === 'tools' || filter === 'errors';
  const Icon = errors.length ? XCircle : toolNames.length ? Wrench : step.messages.length ? MessageSquare : Brain;
  return <details className={`timeline-event timeline-step ${errors.length ? 'has-error' : ''}`}>
    <summary>
      <Icon className="event-svg" aria-hidden="true" />
      <span className="event-summary"><strong>Step {index + 1} · {title}</strong>{preview && <span>{preview}</span>}</span>
      <span className="token-chips">
        {step.durationMs !== undefined && <b>{step.durationMs < 1000 ? `${step.durationMs}ms` : `${(step.durationMs / 1000).toFixed(1)}s`}</b>}
        {usage.input !== undefined && <b>in {compact(usage.input)}</b>}
        {cache.read !== undefined && <b>cached {compact(cache.read)}</b>}
        {usage.output !== undefined && <b>out {compact(usage.output)}</b>}
        {usage.reasoning !== undefined && <b>reasoning {compact(usage.reasoning)}</b>}
      </span>
      <ChevronDown className="event-chevron" aria-hidden="true" />
    </summary>
    <div className="event-body">
      {showReasoning && step.reasoning.map((event, reasoningIndex) => <section className="reasoning-block" key={`reasoning-${reasoningIndex}`}><h3><Brain aria-hidden="true" /> Reasoning</h3><div className="markdown-message"><ReactMarkdown remarkPlugins={[remarkGfm]}>{event.text || ''}</ReactMarkdown></div></section>)}
      {showTools && step.tools.map((event, toolIndex) => <section className={`tool-card ${hasError(event) ? 'has-error' : ''}`} key={`tool-${toolIndex}`}><header><span>{hasError(event) ? <XCircle aria-hidden="true" /> : <CheckCircle2 aria-hidden="true" />}<strong>{event.tool || 'Tool'}</strong></span><small>{event.status || 'observed'}</small></header>{event.input !== undefined && <div><h3>Parameters</h3><pre>{json(event.input)}</pre></div>}{event.output !== undefined && <div><h3>Result</h3><pre>{json(event.output)}</pre></div>}{event.error !== undefined && <div className="error-block"><h3>Error</h3><pre>{json(event.error)}</pre></div>}</section>)}
      {showMessages && step.messages.map((event, messageIndex) => <article className="message assistant compact" key={`message-${messageIndex}`}><div className="message-role">Assistant</div><div className="markdown-message"><ReactMarkdown remarkPlugins={[remarkGfm]}>{event.text || ''}</ReactMarkdown></div></article>)}
    </div>
  </details>;
}

export function TranscriptViewer({ events, instruction, truncated, warnings, rawUrl }: { events: TranscriptEvent[]; instruction?: string; truncated: boolean; warnings: string[]; rawUrl?: string }) {
  const [filter, setFilter] = useState<Filter>('all');
  const summary = useMemo(() => summarizeTranscript(events), [events]);
  const finalMessage = summary.finalMessages.at(-1);
  const visible = summary.steps.filter((step) => stepMatches(step, filter));
  return <section className="transcript" aria-labelledby="transcript-title">
    <div className="utility-heading"><div><h2 id="transcript-title">Transcript</h2><p>{summary.steps.length} steps · {summary.toolCalls} tools · {events.filter(isReasoning).length} reasoning</p></div>{rawUrl && <a href={rawUrl} download>Raw JSONL</a>}</div>
    {(truncated || warnings.length > 0) && <div className="notice">{truncated && <p>Display truncated at 500 events.</p>}{warnings.map((warning) => <p key={warning}>{warning}</p>)}</div>}
    <div className="transcript-filters" role="group" aria-label="Filter transcript">{([['all', 'All'], ['messages', 'Messages'], ['reasoning', 'Reasoning'], ['tools', 'Tools'], ['errors', 'Errors']] as [Filter, string][]).map(([value, label]) => <button key={value} type="button" aria-pressed={filter === value} onClick={() => setFilter(value)}>{label}</button>)}</div>
    {instruction?.trim() && <article className="message user"><div className="message-role">User</div><div className="markdown-message"><ReactMarkdown remarkPlugins={[remarkGfm]}>{instruction}</ReactMarkdown></div></article>}
    <div className="timeline">{visible.map((step, index) => <Step step={step} index={summary.steps.indexOf(step)} filter={filter} key={index} />)}</div>
    {visible.length === 0 && <p className="empty-state">No matching events.</p>}
    {(filter === 'all' || filter === 'messages') && finalMessage && <article className="message assistant final"><div className="message-role">Assistant · final response</div><div className="markdown-message"><ReactMarkdown remarkPlugins={[remarkGfm]}>{finalMessage.text || ''}</ReactMarkdown></div></article>}
  </section>;
}
