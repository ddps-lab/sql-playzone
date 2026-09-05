// The SQL page has no shared imports. Rebuild its tracked production bundle
// without deploying unrelated differences between legacy assets and sources.
import { build } from 'vite';
import { readFile, writeFile, unlink } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(fileURLToPath(import.meta.url));
const entry = 'assets/js/sql_challenge.js';
const manifestPath = resolve(root, 'static/manifest.json');
const manifest = JSON.parse(await readFile(manifestPath, 'utf8'));
const result = await build({
  root,
  configFile: false,
  build: {
    write: false,
    rollupOptions: { input: { sql_challenge: resolve(root, entry) } },
  },
});
const [chunk] = result.output;
if (result.output.length !== 1 || chunk.type !== 'chunk' || !chunk.isEntry ||
    chunk.imports.length || chunk.dynamicImports.length) {
  throw new Error('SQL page is no longer standalone; review its full asset graph before publishing.');
}
const oldFile = manifest[entry].file;
await writeFile(resolve(root, 'static', chunk.fileName), chunk.code);
manifest[entry] = { file: chunk.fileName, src: entry, isEntry: true };
await writeFile(manifestPath, JSON.stringify(manifest, null, 2) + '\n');
if (oldFile !== chunk.fileName && !Object.values(manifest).some(item => item.file === oldFile)) {
  await unlink(resolve(root, 'static', oldFile));
}
