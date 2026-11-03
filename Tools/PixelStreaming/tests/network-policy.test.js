'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { validateConfig } = require('../server/service');
const { sameOrigin, clientAddress } = require('../server/network-policy');

const primary = 'https://warehouse-sim.iyunquna.com';
const backup = 'http://47.96.135.179:8080';
const config = extra => validateConfig({ executablePath: process.execPath, networkMode: 'public', publicUrl: primary, externalTlsTermination: true, ...extra });
const request = (host, origin, remoteAddress = '10.100.185.20') => ({ headers: { host, ...(origin === undefined ? {} : { origin }) }, socket: { remoteAddress } });

test('backup public URL is optional and normalizes a full HTTP origin', () => {
  assert.equal(config().backupPublicUrl, '');
  assert.equal(config({ backupPublicUrl: '' }).backupPublicUrl, '');
  assert.equal(config({ backupPublicUrl: backup + '/' }).backupPublicUrl, backup);
  assert.equal(config({ backupPublicUrl: 'http://backup.example:80/' }).backupPublicUrl, 'http://backup.example');
  assert.equal(config({ backupPublicUrl: 'http://[2001:db8::1]:8080' }).backupPublicUrl, 'http://[2001:db8::1]:8080');
});

test('backup public URL rejects malformed origins and nonstring configuration', () => {
  const invalid = [null, false, 42, [], {}, undefined,
    'https://backup.example', 'ws://backup.example', '//backup.example', 'http:backup.example',
    'http://user@backup.example', 'http://@backup.example', 'http://user:pass@backup.example',
    'http://backup.example/a', 'http://backup.example//', 'http://backup.example?', 'http://backup.example#',
    'http://backup.example?x=1', 'http://backup.example#x', 'http://*.example', 'http://backup%2eexample',
    'http://backup.example:0', 'http://backup.example:65536', 'http://backup.example:-1', 'http://backup.example:',
    'http://backup.example\\', ' http://backup.example', 'http://backup.example ',
    'http://back up.example', 'http://backup.example\t', 'http://backup.example\n', 'http://backup.example\r',
    'http://backup.example\0', 'http://backup.example\x01', 'http://backup.example\x7f',
    'http://[not-ipv6]', 'http://-backup.example', 'http://backup-.example', 'http://backup..example', 'http://backup.example.'];
  for (const value of invalid) assert.throws(() => config({ backupPublicUrl: value }), undefined, JSON.stringify(value));
});

test('backup public URL requires external TLS with an HTTPS primary and distinct host', () => {
  for (const overrides of [
    { networkMode: 'lan', externalTlsTermination: false },
    { externalTlsTermination: false, trustProxy: true },
    { publicUrl: 'http://warehouse.example', externalTlsTermination: false },
    { publicUrl: 'https://warehouse.example:8080', backupPublicUrl: 'http://warehouse.example:8080' },
    { publicUrl: 'https://warehouse.example', backupPublicUrl: 'http://warehouse.example:80' }
  ]) assert.throws(() => config({ backupPublicUrl: backup, ...overrides }));
});

test('dual origins require matching Host and Origin, including missing-Origin requests', () => {
  const c = config({ backupPublicUrl: backup });
  const p = new URL(primary).host, b = new URL(backup).host;
  for (const [host, origin] of [[p, primary], [b, backup], [p, undefined], [b, undefined]]) {
    assert.equal(sameOrigin(request(host, origin), c), true, `${host} / ${origin}`);
  }
  for (const [host, origin] of [[p, backup], [b, primary], [p, 'http://' + p], [b, 'https://' + b],
    ['47.96.135.179:8081', backup], ['evil.example', primary], ['evil.example', undefined],
    [p, 'null'], [b, backup + '/'], ['127.0.0.1:' + c.httpPort, undefined]]) {
    assert.equal(sameOrigin(request(host, origin), c), false, `${host} / ${origin}`);
  }
  const forged = request('evil.example', primary);
  forged.headers['x-forwarded-host'] = p; forged.headers['x-forwarded-proto'] = 'https'; forged.headers['x-forwarded-for'] = '127.0.0.1';
  assert.equal(sameOrigin(forged, c), false);
  assert.equal(clientAddress(forged, c), '10.100.185.20');
});

test('dual origin policy retains the old local exception and old single-origin restrictions', () => {
  const c = config({ backupPublicUrl: backup }), localHost = '127.0.0.1:' + c.httpPort;
  for (const origin of [undefined, 'http://' + localHost, primary]) assert.equal(sameOrigin(request(localHost, origin, '127.0.0.1'), c), true);
  assert.equal(sameOrigin(request(localHost, backup, '127.0.0.1'), c), false);
  assert.equal(sameOrigin(request('evil.example', primary, '127.0.0.1'), c), false);
  assert.equal(sameOrigin(request(new URL(backup).host, backup), config()), false);
  assert.equal(sameOrigin(request(new URL(primary).host, primary), config()), true);
});
