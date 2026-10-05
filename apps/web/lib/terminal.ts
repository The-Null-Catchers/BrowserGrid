// Render terminal output as plain React text; never interpret escape sequences as HTML.
export function plainTerminalText(value: string): string {
  return value
    .replace(/\u001b\[[0-?]*[ -/]*[@-~]/g, '')
    .replace(/\u001b\][^\u0007\u001b]*(?:\u0007|\u001b\\)/g, '');
}
