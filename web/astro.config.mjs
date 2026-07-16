import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import tailwindcss from '@tailwindcss/vite';

const base = process.env.BASE_PATH || '/coding-agent-evals/';
export default defineConfig({
  site: process.env.SITE_URL || 'https://sargunv.github.io',
  base: base.startsWith('/') ? base : `/${base}`,
  output: 'static',
  trailingSlash: 'always',
  integrations: [react()],
  vite: { plugins: [tailwindcss()] },
});
