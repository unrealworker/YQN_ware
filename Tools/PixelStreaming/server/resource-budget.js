'use strict';
const fs = require('node:fs');
const path = require('node:path');

class BudgetPolicy {
  constructor(config) {
    this.config = config; this.currentFps = config.fps; this.count = 0;
    this.warmupUntil = 0; this.holdUntil = 0; this.pressureCount = 0;
    this.pressureTarget = null; this.healthyCount = 0; this.lastProbeAt = 0; this.lastSamples = new Map();
  }
  update(metrics, now = Date.now()) {
    const count = metrics.length;
    if (count !== this.count) {
      this.count = count; this.warmupUntil = now + 5000; this.holdUntil = 0;
      this.pressureCount = 0; this.pressureTarget = null; this.healthyCount = 0; this.lastProbeAt = now; this.lastSamples.clear();
      this.currentFps = Math.max(5, Math.floor(this.config.fps / Math.max(1, count)));
    }
    if (this.config.mode === 'shared' || this.config.adaptiveResourceBudget === false || count <= 1) return this.currentFps = this.config.fps;
    if (now < this.warmupUntil) return this.currentFps;
    // Every instance must acknowledge the current cap before its measurements inform another.
    // Require a new sample from every instance; repeated polling is not repeated evidence.
    const keys = metrics.map((m, i) => m?.id ?? String(i));
    const valid = new Set(keys).size === count && metrics.every(m => m
      && Number.isFinite(m.receivedAt) && now >= m.receivedAt && now - m.receivedAt <= 5000
      && m.appliedFps === this.currentFps && Number.isFinite(m.actualFps) && m.actualFps >= 0 && m.actualFps <= 1000);
    if (!valid) { this.pressureCount = 0; this.healthyCount = 0; return this.currentFps; }
    if (!metrics.every((m, i) => m.receivedAt > (this.lastSamples.get(keys[i]) ?? -Infinity))) return this.currentFps;
    metrics.forEach((m, i) => this.lastSamples.set(keys[i], m.receivedAt));
    // GPU frame timestamps include contention/waiting across processes. They remain
    // diagnostics only: summing them incorrectly throttles already healthy streams.
    const actual = Math.min(...metrics.map(m => m.actualFps));
    if (now >= this.holdUntil) this.pressureTarget = null;
    if (actual < this.currentFps * 0.85) {
      this.healthyCount = 0;
      if (++this.pressureCount >= 2) {
        const fairCap = Math.max(5, Math.floor(actual * 0.97));
        this.pressureTarget = this.pressureTarget === null ? fairCap : Math.min(this.pressureTarget, fairCap);
        this.holdUntil = now + 12000; this.pressureCount = 0;
      }
      if (this.pressureTarget === null) return this.currentFps;
    } else this.pressureCount = 0;
    if (now < this.holdUntil && this.pressureTarget !== null) {
      this.healthyCount = 0;
      return this.currentFps = Math.max(this.pressureTarget, this.currentFps - 8);
    }
    this.pressureTarget = null;
    if (actual < this.currentFps * 0.95) { this.healthyCount = 0; return this.currentFps; }
    if (++this.healthyCount < 2 || now - this.lastProbeAt < 4000) return this.currentFps;
    this.healthyCount = 0; this.lastProbeAt = now;
    return this.currentFps = Math.min(this.config.fps, this.currentFps + 2);
  }
}

function readMetrics(dir, now = Date.now()) {
  try {
    const file = path.join(dir, 'metrics.json'); const stat = fs.statSync(file);
    if (stat.size > 8192 || now - stat.mtimeMs > 5000 || stat.mtimeMs > now + 1000) return null;
    const m = JSON.parse(fs.readFileSync(file, 'utf8'));
    if (m.version !== 1 || !Number.isSafeInteger(m.sequence) || m.sequence < 0 || !Number.isFinite(m.appliedFps) || m.appliedFps < 5 || m.appliedFps > 120 || !Number.isFinite(m.actualFps) || m.actualFps < 0 || m.actualFps > 1000) return null;
    return { receivedAt: stat.mtimeMs, sequence: m.sequence, appliedFps: m.appliedFps, actualFps: m.actualFps, gpuMs: Number.isFinite(m.gpuMs) && m.gpuMs > 0 && m.gpuMs <= 1000 ? m.gpuMs : null, screenPercentage: Number.isFinite(m.screenPercentage) ? m.screenPercentage : null };
  } catch { return null; }
}
function writeBudget(dir, config, fps, sequence) {
  const file = path.join(dir, 'budget.json');
  const budget = { version: 1, sequence, fps, minBitrateMbps: config.minBitrateMbps, startBitrateMbps: config.startBitrateMbps, maxBitrateMbps: config.maxBitrateMbps };
  fs.writeFileSync(file + '.tmp', JSON.stringify(budget)); fs.renameSync(file + '.tmp', file);
}
module.exports = { BudgetPolicy, readMetrics, writeBudget };
