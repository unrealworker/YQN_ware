import { build } from 'esbuild';
import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
const root = path.dirname(fileURLToPath(import.meta.url));
const output = path.resolve(root, '../../Content/GHSTwinUI/web');
await build({
  absWorkingDir: root, entryPoints: ['src/runtime.jsx'], outfile: path.join(output, 'motion.js'),
  bundle: true, minify: true, format: 'iife', target: ['chrome90'],
  define: { 'process.env.NODE_ENV': '"production"' }, legalComments: 'linked',
  jsx: 'automatic', charset: 'utf8', logLevel: 'info'
});
const licenses = [
  ['React Bits CountUp', 'src/react-bits/LICENSE.md'],
  ['React', 'node_modules/react/LICENSE'], ['React DOM', 'node_modules/react-dom/LICENSE'],
  ['Motion', 'node_modules/motion/LICENSE.md'], ['ECharts', 'node_modules/echarts/LICENSE'],
  ['ZRender', 'node_modules/zrender/LICENSE']
];
let notices = '# GHS UI motion — third-party notices\n\nReact Bits source: https://github.com/DavidHDev/react-bits/blob/main/src/content/TextAnimations/CountUp/CountUp.jsx\nVendored from the existing project copy on 2026-10-27.\n\n';
for (const [name, file] of licenses) notices += `## ${name}\n\n${await readFile(path.join(root, file), 'utf8')}\n\n`;
await writeFile(path.join(output, 'motion-NOTICES.txt'), notices.trimEnd() + '\n');
const legalPath = path.join(output, 'motion.js.LEGAL.txt');
const legal = await readFile(legalPath, 'utf8');
await writeFile(legalPath, legal.split('\n').map(line => line.trimEnd()).join('\n').trimEnd() + '\n');
