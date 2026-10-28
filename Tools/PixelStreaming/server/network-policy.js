'use strict';
const fs = require('node:fs');
const net = require('node:net');
const crypto = require('node:crypto');

const NETWORK_DEFAULTS = { maxViewers: 10, networkMode: 'lan', publicUrl: '', accessProtectionEnabled: false, accessCode: '', tlsCertPath: '', tlsKeyPath: '', trustProxy: false, externalTlsTermination: false, stunUrl: '', turnUrl: '', turnUsername: '', turnPassword: '' };
function validateNetwork(c) {
  if (!Number.isInteger(c.maxViewers) || c.maxViewers < 1 || c.maxViewers > 10) throw Error('人数上限必须是1至10的整数');
  if (!['lan', 'public'].includes(c.networkMode)) throw Error('网络模式必须是 lan 或 public');
  if (typeof c.accessProtectionEnabled !== 'boolean') throw Error('accessProtectionEnabled 必须是布尔值');
  if (typeof c.trustProxy !== 'boolean') throw Error('trustProxy 必须是布尔值');
  if (typeof c.externalTlsTermination !== 'boolean') throw Error('externalTlsTermination 必须是布尔值');
  if (c.trustProxy && c.networkMode !== 'public') throw Error('本机反向代理仅适用于公网模式');
  if (c.externalTlsTermination && c.networkMode !== 'public') throw Error('云负载均衡 HTTPS 仅适用于公网模式');
  for (const key of ['publicUrl', 'accessCode', 'tlsCertPath', 'tlsKeyPath', 'stunUrl', 'turnUrl', 'turnUsername', 'turnPassword']) {
    if (typeof c[key] !== 'string' || c[key].length > 4096 || /[\r\n\0]/.test(c[key])) throw Error('无效网络配置：' + key);
  }
  if (c.publicUrl) {
    let url; try { url = new URL(c.publicUrl); } catch { throw Error('公网地址必须是完整的 http:// 或 https:// 地址'); }
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash || url.pathname !== '/') throw Error('公网地址只能包含协议、域名或IP和端口');
    c.publicUrl = url.origin;
  }
  if (c.networkMode === 'public' && !c.publicUrl) throw Error('公网模式需要公网地址');
  if (c.accessProtectionEnabled && (!c.accessCode.trim() || c.accessCode.length < 12)) throw Error('开启安全访问仓库后需要至少12字符的访问码');
  if (!!c.tlsCertPath !== !!c.tlsKeyPath) throw Error('HTTPS 证书和私钥必须同时提供');
  for (const key of ['tlsCertPath', 'tlsKeyPath']) if (c[key] && !fs.statSync(c[key], { throwIfNoEntry: false })?.isFile()) throw Error('找不到 HTTPS 文件：' + key);
  if (c.trustProxy && c.tlsCertPath) throw Error('本机反向代理和服务直连 HTTPS 请选择一种');
  if (c.externalTlsTermination && (c.trustProxy || c.tlsCertPath)) throw Error('云负载均衡、本机反向代理和服务直连 HTTPS 请选择一种');
  if (c.networkMode === 'public') {
    if (c.publicUrl.startsWith('https:') && !c.tlsCertPath && !c.trustProxy && !c.externalTlsTermination) throw Error('HTTPS 公网地址需要证书、本机反向代理或云负载均衡 HTTPS');
    if (c.publicUrl.startsWith('http:') && (c.tlsCertPath || c.trustProxy || c.externalTlsTermination)) throw Error('已启用 HTTPS 接入，公网地址应使用 https://');
  }
  for (const [key, schemes] of [['stunUrl', ['stun:', 'stuns:']], ['turnUrl', ['turn:', 'turns:']]]) {
    if (!c[key]) continue;
    // ICE URI syntax is scheme:host:port, not an HTTP URL. Reject embedded credentials.
    if (!schemes.some(s => c[key].startsWith(s)) || !/^(?:stuns?|turns?):(?:\[[a-fA-F0-9:]+\]|[a-zA-Z0-9.-]+)(?::\d{1,5})?(?:\?transport=(?:udp|tcp))?$/.test(c[key])) throw Error('无效 STUN/TURN 地址：' + key);
    const match = c[key].match(/:(\d+)(?:\?|$)/); if (match && (+match[1] < 1 || +match[1] > 65535)) throw Error('STUN/TURN 端口必须是1至65535');
  }
  if (c.turnUrl && (!c.turnUsername || !c.turnPassword)) throw Error('TURN 服务需要用户名和密码');
  if (!c.turnUrl && (c.turnUsername || c.turnPassword)) throw Error('请填写 TURN 服务地址');
  return c;
}
function iceServers(c) {
  const result = [];
  if (c.stunUrl) result.push({ urls: [c.stunUrl] });
  if (c.turnUrl) result.push({ urls: [c.turnUrl], username: c.turnUsername, credential: c.turnPassword });
  return result;
}
const loopback = address => ['127.0.0.1', '::1', '::ffff:127.0.0.1'].includes(address);
function clientAddress(req, c) {
  // External TLS termination changes only the transport arrangement, never the
  // trust boundary for forwarded headers. Remote ALB peers retain socket IPs.
  if (c.trustProxy && loopback(req.socket.remoteAddress)) {
    const forwarded = String(req.headers['x-forwarded-for'] || '').split(',').at(-1).trim();
    if (net.isIP(forwarded)) return forwarded;
  }
  return String(req.socket.remoteAddress || '').replace(/^::ffff:/, '');
}
function sameOrigin(req, c) {
  const native = (c.tlsCertPath ? 'https://' : 'http://') + req.headers.host;
  if (c.networkMode === 'public') {
    // Disabling the access-code gate never disables browser Origin/Host guards.
    // WebSockets still require a server-issued session token in every mode.
    const expectedHost = new URL(c.publicUrl).host;
    const local = loopback(req.socket.remoteAddress) && ['127.0.0.1:' + c.httpPort, 'localhost:' + c.httpPort].includes(req.headers.host);
    if (req.headers.host !== expectedHost && !local) return false;
    return !req.headers.origin || req.headers.origin === c.publicUrl || (local && req.headers.origin === native);
  }
  return !req.headers.origin || req.headers.origin === native;
}
function secretEqual(a, b) {
  if (typeof a !== 'string' || a.length > 4096) return false;
  return crypto.timingSafeEqual(crypto.createHash('sha256').update(a).digest(), crypto.createHash('sha256').update(b).digest());
}
module.exports = { NETWORK_DEFAULTS, validateNetwork, iceServers, clientAddress, sameOrigin, secretEqual };
