// Public diagnostics: allowlisted commit only, never process.env or host IDs.
const fs = require('fs');
const path = require('path');
const commit = process.env.RENDER_GIT_COMMIT || process.env.APP_BUILD_COMMIT || '';
fs.writeFileSync(path.join(__dirname, '../public/build-info.json'), JSON.stringify({
  commit: /^[0-9a-f]{7,40}$/i.test(commit) ? commit : 'unknown',
  stream_protocol: 2,
}) + '\n');
