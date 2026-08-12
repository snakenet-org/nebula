// @ai-purpose: Small shared frontend helpers with no other home — shadcn-vue's `cn()` class-merge
//   plus a couple of small string helpers used by more than one view.
// @ai-context: stripLineBreaks/truncate (2026-08-12, GitHub #6/#7) were pulled out here specifically
//   because both EnvironmentsView.vue AND ProjectView.vue needed the same behavior (line-break
//   stripping on an editable field, 250-char ellipsis truncation in a table cell) — see each
//   function's own comment for the fuller rationale.
// @version: 1.1.0
// @author: Marc Fiedler <marc@snakenet.org>
// @date: 2026-08-12

import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}

// Strips any pasted \r/\n from a single-line field's value — a plain <input> still accepts a
// pasted line break into its value even though it never renders one (see ProjectView.vue's
// renameValue for the original instance of this pattern; EnvironmentsView.vue reuses it for
// GitHub #6). Applying this on every write, not just on submit, keeps the field's on-screen state
// and its actual value in sync no matter how a line break got in.
export function stripLineBreaks(value) {
  return value.replace(/[\r\n]+/g, "");
}

// Truncates `text` to `maxLength` characters, appending "…" when it was actually cut short — backs
// the 250-char description truncation in the Environments/Project key tables (GitHub #7). Returns
// `text` unchanged (including null/empty) when it's already within the limit.
export function truncate(text, maxLength) {
  if (!text || text.length <= maxLength) return text;
  return `${text.slice(0, maxLength)}…`;
}
