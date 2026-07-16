import { access, readFile, readdir } from 'node:fs/promises';
import path from 'node:path';
const dist = path.resolve('dist');
for (const required of ['index.html','tasks/index.html','models/index.html','glossary/index.html','.nojekyll']) await access(path.join(dist, required));
const html = []; async function walk(dir) { for (const d of await readdir(dir,{withFileTypes:true})) { const p=path.join(dir,d.name); if(d.isDirectory()) await walk(p); else if(d.name.endsWith('.html')) html.push(p); } } await walk(dist);
if (!html.some((f) => f.includes(`${path.sep}runs${path.sep}`))) throw new Error('No static run deep-link pages generated');
for (const file of html) { const source=await readFile(file,'utf8'); if (/href=["']#\//.test(source)) throw new Error(`Hash-only route in ${file}`); if (/<script[^>]*>[^<]*(eval\(|document\.write)/i.test(source)) throw new Error(`Unsafe inline script in ${file}`); }
console.log(`Validated ${html.length} static HTML pages, required routes, and non-hash navigation.`);
