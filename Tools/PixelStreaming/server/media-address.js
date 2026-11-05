'use strict';
const net = require('node:net');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

// An explicit 1:1 EIP mapping for deployments behind an HTTP-only load balancer.
// The private address must belong to the UE host; never infer it from a client.
function validateMediaAddress(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value) || net.isIP(value.privateIp) !== 4 || net.isIP(value.publicIp) !== 4) throw Error('媒体地址映射需要有效 IPv4 地址');
  const [a, b] = value.publicIp.split('.').map(Number);
  if (a === 0 || a === 10 || a === 127 || a >= 224 || (a === 169 && b === 254) || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168) || (a === 100 && b >= 64 && b <= 127)) throw Error('媒体公网地址必须是公网 IPv4');
  return { privateIp: value.privateIp, publicIp: value.publicIp };
}

function loadMediaAddress(networkMode, value, file = path.join(__dirname, 'media-address.json')) {
  if (value === undefined && networkMode === 'public') {
    try { value = JSON.parse(fs.readFileSync(file, 'utf8').replace(/^\uFEFF/, '')); }
    catch (error) { if (error.code === 'ENOENT') return undefined; throw error; }
  }
  if (value === undefined) return undefined;
  const mapping = validateMediaAddress(value);
  const addresses = Object.values(os.networkInterfaces()).flat().filter(Boolean).map(address => address.address);
  if (!addresses.includes(mapping.privateIp)) throw Error('媒体映射的内网地址不属于本机，请更新 server/media-address.json');
  return mapping;
}

function publicMediaCandidate(candidate, mapping) {
  if (!mapping || !candidate || typeof candidate.candidate !== 'string') return null;
  const fields = candidate.candidate.trim().split(/\s+/);
  if (!/^candidate:[A-Za-z0-9+/]{1,32}$/.test(fields[0]) || !/^[1-9]\d{0,2}$/.test(fields[1]) || Number(fields[1]) > 256 || fields[2]?.toLowerCase() !== 'udp' || fields[4] !== mapping.privateIp || fields[6] !== 'typ' || fields[7] !== 'host') return null;
  const port = Number(fields[5]), priority = Number(fields[3]);
  if (!/^\d{1,5}$/.test(fields[5]) || port < 50000 || port > 50199 || !/^\d{1,10}$/.test(fields[3]) || !Number.isSafeInteger(priority) || priority < 0 || priority > 0xffffffff) return null;
  const hostIp = fields[4];
  fields[0] = 'candidate:ghspublic' + fields[0].slice(10, 33);
  // RFC 8445: prefer the original host candidate on LAN, srflx on public NAT.
  fields[3] = String(100 * 2 ** 24 + (priority & 0xffffff));
  fields[4] = mapping.publicIp;
  fields[7] = 'srflx';
  fields.splice(8, 0, 'raddr', hostIp, 'rport', String(port));
  return { ...candidate, candidate: fields.join(' ') };
}

module.exports = { validateMediaAddress, loadMediaAddress, publicMediaCandidate };
