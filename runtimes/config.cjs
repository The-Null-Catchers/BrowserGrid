const path = require('node:path');
const defaultCommand = '/opt/browsergrid/node_modules/.bin/playwright';
function executionCommand(command, cwd, inline) {
  const args = [...command];
  if (!inline && args[0] === defaultCommand) {
    args[0] = path.join(cwd, 'node_modules/.bin/playwright');
  }
  return args;
}
function generatedConfigSource(userConfig, config) {
  const original = userConfig
    ? `import original from ${JSON.stringify(userConfig)};\n`
    : 'const original = {};\n';
  return original + `const enforced=${JSON.stringify(config)};\n` +
    'export default {...original,...enforced,use:{...original.use,...enforced.use}};\n';
}
module.exports = { executionCommand, generatedConfigSource };
