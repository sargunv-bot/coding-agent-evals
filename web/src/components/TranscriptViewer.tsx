import type { TranscriptEvent } from '../lib/types';
import { humanizeEnum } from '../lib/format';
import { Conversation, Message, Tool } from './ai-elements/VendoredElements';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const json = (value: unknown) => JSON.stringify(value, null, 2);
const isText = (event: TranscriptEvent) => event.type === 'text' || event.type === 'assistant';
const isTool = (event: TranscriptEvent) => event.type === 'tool_use' || event.type === 'tool' || Boolean(event.tool);

export function summarizeTranscript(events: TranscriptEvent[]) {
  const finalMessages = events.filter(isText);
  const clarifications = events.filter((event) => isTool(event) && event.tool === 'proctor_ask_user');
  const steps: TranscriptEvent[][] = [];
  let current: TranscriptEvent[] = [];
  for (const event of events) {
    if ((event.type === 'step_start' || event.type === 'step-start') && current.length) {
      steps.push(current); current = [];
    }
    current.push(event);
    if (event.type === 'step_finish' || event.type === 'step-finish') {
      steps.push(current); current = [];
    }
  }
  if (current.length) steps.push(current);
  return { finalMessages, clarifications, steps, toolCalls: events.filter(isTool).length };
}

function ToolEvent({ event, open = false }: { event: TranscriptEvent; open?: boolean }) {
  return <Tool name={event.tool || 'Unknown tool'} status={event.status ? humanizeEnum(event.status) : undefined} open={open}>
    {event.input !== undefined && <div><h4 className="font-semibold">Parameters</h4><pre>{json(event.input)}</pre></div>}
    {event.output !== undefined && <div><h4 className="font-semibold">Result</h4><pre>{typeof event.output === 'string' ? event.output : json(event.output)}</pre></div>}
    {event.error !== undefined && <div className="alert alert-error"><div><h4 className="font-semibold">Error</h4><pre>{json(event.error)}</pre></div></div>}
  </Tool>;
}

function Step({ events, index }: { events: TranscriptEvent[]; index: number }) {
  const tools = events.filter(isTool);
  const reasoning = events.filter((event) => event.type === 'reasoning');
  const finish = events.find((event) => event.type === 'step_finish' || event.type === 'step-finish');
  const names = [...new Set(tools.map((event) => event.tool || 'unknown'))];
  return <details className="trace-step">
    <summary><span>Step {index + 1}</span><span className="step-meta">{tools.length ? `${tools.length} tool call${tools.length === 1 ? '' : 's'} · ${names.join(', ')}` : 'No tool call'}</span></summary>
    <div className="trace-step-body">
      {reasoning.map((event, reasoningIndex) => <details key={`reasoning-${reasoningIndex}`}><summary>Assistant reasoning</summary><p className="mt-3 whitespace-pre-wrap">{event.text || 'No reasoning text supplied.'}</p></details>)}
      {tools.map((event, toolIndex) => <ToolEvent event={event} key={`tool-${toolIndex}`} />)}
      {finish && <details><summary>Usage and completion event</summary><pre className="mt-3">{json(finish.usage ?? finish.raw)}</pre></details>}
      {events.filter((event) => !['step_start','step-start','step_finish','step-finish','reasoning'].includes(event.type) && !isTool(event) && !isText(event)).map((event, unknownIndex) => <details key={`unknown-${unknownIndex}`}><summary>Unknown event · {event.type}</summary><pre className="mt-3">{json(event.raw)}</pre></details>)}
    </div>
  </details>;
}

export function TranscriptViewer({ events, truncated, warnings, rawUrl }: { events: TranscriptEvent[]; truncated: boolean; warnings: string[]; rawUrl?: string }) {
  const summary = summarizeTranscript(events);
  return <section aria-labelledby="transcript-heading">
    <div className="mb-4 flex flex-wrap items-start justify-between gap-3"><div><h2 id="transcript-heading" className="text-xl font-bold">Agent transcript</h2><p className="text-sm opacity-70">{summary.steps.length} steps · {summary.toolCalls} tool calls · {summary.clarifications.length} clarification{summary.clarifications.length === 1 ? '' : 's'}</p></div>{rawUrl && <a className="btn btn-sm btn-outline" href={rawUrl} download>Download raw JSONL</a>}</div>
    {(truncated || warnings.length > 0) && <div className="alert alert-warning mb-4" role="status">{truncated && <p>Display truncated after 500 events; the complete raw JSONL remains available.</p>}{warnings.map((warning) => <p key={warning}>{warning}</p>)}</div>}

    {summary.clarifications.length > 0 && <section className="mb-5" aria-labelledby="clarifications-heading"><h3 id="clarifications-heading" className="mb-3 font-bold">Clarifications</h3>{summary.clarifications.map((event, index) => <ToolEvent event={event} open key={index} />)}</section>}

    <section className="mb-5" aria-labelledby="final-answer-heading"><div className="mb-3"><h3 id="final-answer-heading" className="font-bold">Final answer</h3><p className="text-sm opacity-70">Candidate-reported summary; the verifier above remains authoritative.</p></div><Conversation>{summary.finalMessages.map((event, index) => <Message role="assistant" key={index}><div className="markdown-message"><ReactMarkdown remarkPlugins={[remarkGfm]}>{event.text || ''}</ReactMarkdown></div></Message>)}</Conversation>{summary.finalMessages.length === 0 && <p className="panel">No final assistant message was committed.</p>}</section>

    <details className="work-trace panel"><summary><strong>Full agent work trace</strong><span className="ml-2 text-sm font-normal opacity-70">{summary.steps.length} grouped steps</span></summary><div className="mt-4 space-y-2">{summary.steps.map((step, index) => <Step events={step} index={index} key={index} />)}</div></details>
    {events.length === 0 && <p className="panel">No displayable transcript events are committed.</p>}
  </section>;
}
