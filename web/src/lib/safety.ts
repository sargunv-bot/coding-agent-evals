import { lstat, realpath } from 'node:fs/promises';
import path from 'node:path';

export function safeRelativePath(value: string): string {
  if (!value || path.isAbsolute(value) || value.includes('\\') || value.split('/').some((part) => part === '..' || part === '' || part === '.')) throw new Error(`Unsafe relative path: ${value}`);
  return value;
}
export async function containedFile(root: string, relative: string): Promise<string> {
  safeRelativePath(relative);
  const canonicalRoot = await realpath(root);
  const candidate = path.resolve(root, relative);
  const stat = await lstat(candidate);
  if (stat.isSymbolicLink() || !stat.isFile()) throw new Error(`Evidence must be a regular non-symlink file: ${relative}`);
  const canonical = await realpath(candidate);
  if (canonical !== canonicalRoot && !canonical.startsWith(`${canonicalRoot}${path.sep}`)) throw new Error(`Path escapes data root: ${relative}`);
  return canonical;
}
export function validateHttpUrl(value: unknown, field: string): string | undefined {
  if (value == null || value === '') return undefined;
  if (typeof value !== 'string') throw new Error(`${field} must be an HTTP(S) URL`);
  const parsed = new URL(value);
  if (!['http:', 'https:'].includes(parsed.protocol)) throw new Error(`${field} must be an HTTP(S) URL`);
  return parsed.href;
}
