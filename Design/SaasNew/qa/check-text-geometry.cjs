'use strict';
const fs = require('fs');
const path = require('path');
const { convert } = require('../dom-to-pen.cjs');
const directory = path.resolve(__dirname, '../runtime/dom');
const report = { checkedAt: new Date().toISOString(), files: 0, singleLineRuns: 0, multiLineRuns: 0, inputValues: 0, errors: [], numericClipRisks: [], fonts: {} };
for (const file of fs.readdirSync(directory).filter(name => name.endsWith('.json'))) {
  report.files++;
  const snapshot = JSON.parse(fs.readFileSync(path.join(directory, file), 'utf8'));
  const { root } = convert(snapshot, file.replace('.json', ''));
  function walk(node, x, y, clips) {
    x += node.x || 0; y += node.y || 0;
    if (node.type === 'text') {
      report.fonts[node.fontFamily] = (report.fonts[node.fontFamily] || 0) + 1;
      const isDom = node.metadata?.source === 'DOM text run';
      if (isDom) {
        if (node.metadata.noWrap) {
          report.singleLineRuns++;
          if (node.textGrowth) report.errors.push({file, id: node.id, problem: 'Single-line DOM text retained fixed growth'});
          const rightMargin = Math.min(...clips.map(clip => clip.right - (x + node.width)));
          if (/\d/.test(node.content) && rightMargin < 4) report.numericClipRisks.push({file, id: node.id, text: node.content, rightMargin, sourceWidth: node.width});
        } else {
          report.multiLineRuns++;
          if (node.textGrowth !== 'fixed-width-height') report.errors.push({file, id: node.id, problem: 'Multiline DOM text lost original geometry'});
        }
      }
      if (node.metadata?.inputType) {
        report.inputValues++;
        if (node.textGrowth || !node.metadata.noWrap) report.errors.push({file, id: node.id, problem: 'Input value can wrap'});
      }
    }
    const next = node.clip ? [...clips, { right: x + node.width }] : clips;
    for (const child of node.children || []) walk(child, x, y, next);
  }
  walk(root, 0, 0, []);
}
report.passed = !report.errors.length && !report.numericClipRisks.length;
report.scope = 'Checks original DOM glyph bounds against converted clipping ancestors; final Figma font metrics still require inspection.';
fs.writeFileSync(path.join(__dirname, 'text-geometry-verification.json'), JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
if (!report.passed) process.exitCode = 1;
