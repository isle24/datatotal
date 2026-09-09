import test from 'node:test';
import assert from 'node:assert/strict';
import { manifest, targets } from '../../scripts/desktop-artifacts.mjs';
test('desktop channel requires signed packages for all three targets', () => {
  const files = {};
  for (const [target, name] of Object.entries(targets)) {
    const file = `Traffic-Lens-0.3.0-${name}${target.startsWith('darwin') ? '.app.tar.gz' : '-setup.exe'}`;
    files[file] = true; files[file + '.sig'] = Buffer.from('untrusted comment: test fixture').toString('base64');
  }
  const result = manifest('0.3.0', files);
  assert.equal(Object.keys(result.platforms).length, 3);
  assert.match(result.platforms['windows-x86_64'].url, /desktop-v0.3.0\/Traffic-Lens-0.3.0-Windows-x64-setup.exe$/);
  delete files['Traffic-Lens-0.3.0-macOS-x64.app.tar.gz.sig'];
  assert.throws(() => manifest('0.3.0', files), /Missing signed artifact/);
});
