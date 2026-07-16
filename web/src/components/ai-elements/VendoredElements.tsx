/*
 * Adapted from Vercel AI Elements Conversation, Message, and Tool source patterns.
 * Upstream: https://github.com/vercel/ai-elements/tree/0c1f5e8c75273f0e95c8faa031544a8aa2bb1a5b/packages/elements/src
 * Apache-2.0. Modifications: dependency-free semantic HTML, static rendering,
 * evaluation-event statuses, and accessibility labels for this results browser.
 */
import type { ReactNode } from 'react';
export function Conversation({ children }: { children: ReactNode }) { return <section className="space-y-4" aria-label="Agent conversation">{children}</section>; }
export function Message({ role, children }: { role: 'assistant' | 'system' | 'unknown'; children: ReactNode }) { return <article className="panel" data-role={role}><header className="eyebrow mb-2">{role === 'assistant' ? 'Assistant' : role}</header>{children}</article>; }
export function Tool({ name, status, open = false, children }: { name: string; status?: string; open?: boolean; children: ReactNode }) { return <details className="collapse-arrow collapse border border-base-300 bg-base-200" open={open}><summary className="collapse-title"><span className="font-semibold">Tool · {name}</span>{status && <span className="badge badge-outline ml-2">{status}</span>}</summary><div className="collapse-content space-y-3">{children}</div></details>; }
