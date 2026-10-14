const { packager } = require('@electron/packager');
const fs = require('node:fs');
const path = require('node:path');
(async () => {
  const [dir, resources, out] = process.argv.slice(2);
  const results = await packager({ dir, out, name: 'Onbitnuri', executableName: 'Onbitnuri',
    platform: 'win32', arch: 'x64', electronVersion: require('./package.json').devDependencies.electron,
    asar: true, prune: true, overwrite: false });
  for (const result of results) fs.cpSync(resources, path.join(result, 'resources'), { recursive: true });
})().catch(error => { console.error(error); process.exitCode = 1; });
