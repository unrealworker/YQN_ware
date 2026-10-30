'use strict';
const crypto = require('node:crypto');
// Reviewed UE5.8 0.1.3 ESM module; this is not the old UE5.4 UMD patch.
const ORIGINAL_SHA256 = '9355c4522c46b266f01f96cc5c6cf3441bba9b5c0922951a6c4266b646cf83c5';
const PATCH_ID = 'ghs-ue58-session-sdp-v2';
const original = "sdp.replace(/(a=fmtp:\\d+ .*level-asymmetry-allowed=.*)\\r\\n/gm, '$1;x-google-start-bitrate=10000;x-google-max-bitrate=100000\\r\\n')";
const replacement = '(typeof this.config.ghsMungeVideoSDP === "function" ? this.config.ghsMungeVideoSDP(sdp) : sdp)';
const sha256 = text => crypto.createHash('sha256').update(text).digest('hex');

// The pinned Epic archive and its extracted SDK remain unmodified. This one
// generated-module hook removes fixed 10/100 Mbps hints, leaving audio and the
// new capture-time RTP extension unchanged. esbuild then bundles this copy.
// A changed upstream bundle must be explicitly reviewed, never silently patched.
function patchFrontendSDK(source) {
  if (sha256(source) !== ORIGINAL_SHA256) throw Error('Epic SDK SHA256 不匹配，拒绝应用 SDP 补丁');
  if (source.split(original).length !== 2) throw Error('Epic SDK SDP 补丁必须精确匹配一次');
  const code = source.replace(original, replacement);
  return { code, manifest: { patch: PATCH_ID, package: '@epicgames-ps/lib-pixelstreamingfrontend-ue5.8',
    version: '0.1.3', module: 'dist/esm/PeerConnectionController/PeerConnectionController.js', originalSha256: ORIGINAL_SHA256, patchedSha256: sha256(code), replacements: 1 } };
}
module.exports = { patchFrontendSDK };
