'use strict';
const crypto = require('node:crypto');
const ORIGINAL_SHA256 = 'e77704308c953e147ec7a062d1a8ea50f6f4b7931f59e37192ca0deb606686f8';
const PATCH_ID = 'ghs-session-sdp-v1';
const original = 'e.replace(/(a=fmtp:\\d+ .*level-asymmetry-allowed=.*)\\r\\n/gm,"$1;x-google-start-bitrate=10000;x-google-max-bitrate=100000\\r\\n")';
const replacement = '(typeof this.config.ghsMungeVideoSDP==="function"?this.config.ghsMungeVideoSDP(e):e)';
const sha256 = text => crypto.createHash('sha256').update(text).digest('hex');

// The pinned Epic archive and its extracted SDK remain unmodified. This one
// generated-bundle hook removes fixed 10/100 Mbps hints, leaving audio untouched.
// A changed upstream bundle must be explicitly reviewed, never silently patched.
function patchFrontendSDK(source) {
  if (sha256(source) !== ORIGINAL_SHA256) throw Error('Epic SDK SHA256 不匹配，拒绝应用 SDP 补丁');
  if (source.split(original).length !== 2) throw Error('Epic SDK SDP 补丁必须精确匹配一次');
  const code = source.replace(original, replacement);
  return { code, manifest: { patch: PATCH_ID, package: '@epicgames-ps/lib-pixelstreamingfrontend-ue5.4',
    version: '1.1.6', originalSha256: ORIGINAL_SHA256, patchedSha256: sha256(code), replacements: 1 } };
}
module.exports = { patchFrontendSDK };
