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
      // Admission is not proof of contention: keep the selected target until fresh
      // measurements show sustained pressure. Never turn an uncapped request into 5 FPS.
      this.currentFps = this.config.fps;
    }
    if (this.config.fixedFps === true || this.config.fps === 0 || this.config.mode === 'shared' || this.config.adaptiveResourceBudget === false || count <= 1) return this.currentFps = this.config.fps;
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
    if (m.version !== 1 || !Number.isSafeInteger(m.sequence) || m.sequence < 0 || !Number.isInteger(m.appliedFps) || (m.appliedFps !== 0 && (m.appliedFps < 5 || m.appliedFps > 120)) || !Number.isFinite(m.actualFps) || m.actualFps < 0 || m.actualFps > 1000) return null;
    return { receivedAt: stat.mtimeMs, sequence: m.sequence, appliedFps: m.appliedFps, actualFps: m.actualFps, gpuMs: Number.isFinite(m.gpuMs) && m.gpuMs > 0 && m.gpuMs <= 1000 ? m.gpuMs : null, screenPercentage: Number.isFinite(m.screenPercentage) ? m.screenPercentage : null,
      psoActivePrecacheRequests: Number.isSafeInteger(m.psoActivePrecacheRequests) && m.psoActivePrecacheRequests >= 0 ? m.psoActivePrecacheRequests : null,
      standbyMode: ['warming', 'standby', 'active'].includes(m.standbyMode) ? m.standbyMode : null };
  } catch { return null; }
}
function writeBudget(dir, config, fps, sequence, mode) {
  const file = path.join(dir, 'budget.json');
  const budget = { version: 1, sequence, fps, minBitrateMbps: config.minBitrateMbps, startBitrateMbps: config.startBitrateMbps, maxBitrateMbps: config.maxBitrateMbps };
  if (mode !== undefined) { if (!['warming', 'standby', 'active'].includes(mode)) throw Error('Invalid standby budget mode'); budget.mode = mode; }
  fs.writeFileSync(file + '.tmp', JSON.stringify(budget)); fs.renameSync(file + '.tmp', file);
}
function freshMetrics(m, now = Date.now()) { return !!m && Number.isFinite(m.receivedAt) && now >= m.receivedAt && now - m.receivedAt <= 5000; }
function standbyHeadroom(metrics, memory, now = Date.now()) {
  const knownMemory = Number.isFinite(memory?.freeMemoryBytes) && Number.isFinite(memory?.totalMemoryBytes) && memory.totalMemoryBytes > 0;
  if (knownMemory && memory.freeMemoryBytes < Math.max(8 * 1024 ** 3, memory.totalMemoryBytes * .12)) return { allowed: false, reason: 'resources' };
  const knownGpu = Number.isFinite(memory?.gpuFreeMiB) && Number.isFinite(memory?.gpuTotalMiB) && memory.gpuTotalMiB > 0 && Number.isFinite(memory?.gpuReceivedAt) && now >= memory.gpuReceivedAt && now - memory.gpuReceivedAt <= 20000;
  if (knownGpu && memory.gpuFreeMiB < Math.max(3072, memory.gpuTotalMiB * .20)) return { allowed: false, reason: 'resources' };
  // The first unused process can establish telemetry. Once users are active,
  // unknown resources must never justify an extra background UE process.
  if (!metrics.length) return { allowed: true, reason: '' };
  if (!knownMemory) return { allowed: false, reason: 'resources' };
  if (!knownGpu) return { allowed: false, reason: 'unknown-metrics' };
  if (metrics.some(m => !freshMetrics(m, now) || !Number.isFinite(m.gpuMs) || m.gpuMs <= 0 || !Number.isFinite(m.actualFps) || !Number.isFinite(m.appliedFps))) return { allowed: false, reason: 'unknown-metrics' };
  if (metrics.some(m => m.actualFps < (m.appliedFps > 0 ? m.appliedFps * .95 : 30))) return { allowed: false, reason: 'resources' };
  // This is a conservative spare-admission heuristic, NOT measured aggregate GPU
  // utilization. GPU timestamps may include waits: never use it to cap active users.
  if (metrics.reduce((sum, m) => sum + m.gpuMs * m.actualFps / 1000, 0) > .6) return { allowed: false, reason: 'resources' };
  return { allowed: true, reason: '' };
}
module.exports = { BudgetPolicy, readMetrics, writeBudget, freshMetrics, standbyHeadroom };
