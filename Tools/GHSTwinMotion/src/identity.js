// Only semantic metrics are animated; identifiers, dates and table evidence stay literal.
export function parseMetric(text) {
  const match = String(text).trim().match(/^(-?[\d,]+)(\.\d+)?(%)?$/);
  if (!match) return null;
  const value = Number((match[1] + (match[2] || '')).replaceAll(',', ''));
  if (!Number.isFinite(value)) return null;
  return { value, decimals: (match[2] || '').slice(1).length, suffix: match[3] || '', separator: match[1].includes(',') ? ',' : '' };
}
export function equalSpec(a, b) { return JSON.stringify(a) === JSON.stringify(b); }
