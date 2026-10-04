const path = require('node:path');
const { signals } = require('node:os').constants;
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
function processExitCode(code, signal) {
  // Node reports null when a child is killed by a signal. Null must never mean success.
  if (signal) {
    const value = signals[signal];
    return Number.isInteger(value) && value > 0 && value < 128 ? 128 + value : 1;
  }
  return Number.isInteger(code) && code >= 0 && code <= 255 ? code : 1;
}
module.exports = { executionCommand, generatedConfigSource, processExitCode };
