// @ai-purpose: Client-side parser for the Project view's "Upload .env" bulk-add flow.
// @ai-context: Parsing happens entirely client-side, before anything is sent to the bulk-create API
//   (nebular.secrets.create_keys_bulk) — the backend still independently re-checks for duplicate
//   names, this module's only job is turning raw file text into name/value pairs. Comments (a line
//   whose first non-whitespace character is `#`) and blank lines are stripped first, per spec —
//   deliberately NOT stripping a trailing `# ...` after a value on the same line, since that's
//   ambiguous with a value that legitimately contains `#` (quoted or not) and the spec only asked to
//   remove comment LINES. Every remaining line must match `KEY=VALUE` (optionally `export KEY=VALUE`,
//   a common shell/.env convention) or the whole file is rejected — parseEnvFile never returns a
//   partial result, matching the "fail if a single line can't be parsed" requirement.
// @version: 1.0.0
// @author: Marc Fiedler <marc@snakenet.org>
// @date: 2026-08-06

// KEY must look like a shell/env identifier: letters, digits, underscore, not starting with a digit.
const LINE_RE = /^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/;

function unquoteValue(raw) {
  const trimmed = raw.trim();
  if (trimmed.length >= 2) {
    const first = trimmed[0];
    const last = trimmed[trimmed.length - 1];
    if (first === '"' && last === '"') {
      return trimmed
        .slice(1, -1)
        .replace(/\\n/g, '\n')
        .replace(/\\"/g, '"')
        .replace(/\\\\/g, '\\');
    }
    if (first === "'" && last === "'") {
      return trimmed.slice(1, -1);
    }
  }
  return trimmed;
}

/**
 * Parses .env-formatted text into name/value pairs.
 * Returns { items: [{ name, value }], errors: [{ line, content }] } — `errors` is only ever
 * non-empty when at least one non-comment, non-blank line didn't match `KEY=VALUE`; callers should
 * treat any non-empty `errors` as "reject the whole upload," not attempt to use `items` alongside it.
 */
export function parseEnvFile(text) {
  const items = [];
  const errors = [];
  const seenNames = new Set();
  const rawLines = text.split(/\r\n|\r|\n/);

  for (let i = 0; i < rawLines.length; i++) {
    const line = rawLines[i];
    const trimmed = line.trim();
    if (trimmed === '' || trimmed.startsWith('#')) continue;

    const match = LINE_RE.exec(trimmed);
    if (!match) {
      errors.push({ line: i + 1, content: line });
      continue;
    }
    const name = match[1];
    const value = unquoteValue(match[2]);
    if (!seenNames.has(name.toLowerCase())) {
      seenNames.add(name.toLowerCase());
      items.push({ name, value });
    } else {
      // Keep the LAST value for a name repeated within the same file (standard .env/shell semantics
      // — a later line overrides an earlier one) rather than failing the whole upload over it.
      const idx = items.findIndex((item) => item.name.toLowerCase() === name.toLowerCase());
      items[idx] = { name, value };
    }
  }

  return { items, errors };
}
