# Encryption

## What's encrypted, and what isn't

Per the spec this app was built to: **keys are cleartext, values are encrypted.** Concretely:

| Data | At rest |
|---|---|
| Project name, description | cleartext |
| Environment name | cleartext |
| Secret key name (`DATABASE_URL`, ...), description | cleartext |
| **Secret value** | **encrypted** (Fernet token) |
| Project access key | never stored — only a SHA-256 hash + a short display prefix |
| `NEBULAR_MASTER_KEY` | never stored anywhere — read from the environment on every process start |

This is deliberate: key *names* need to stay searchable/sortable/readable in the UI and the
database; only the actual secret material needs to be opaque at rest.

## The master key

`NEBULAR_MASTER_KEY` is set once, when you spawn the container. It can be any string — a real
passphrase, not necessarily a pre-formatted cryptographic key — because `nebular.crypto` derives an
actual 32-byte Fernet key from it:

```
fernet_key = base64.urlsafe_b64encode(sha256(NEBULAR_MASTER_KEY).digest())
```

Every secret value is encrypted with [`cryptography.fernet.Fernet`](https://cryptography.io/en/latest/fernet/)
using that derived key — AES-128 in CBC mode with a SHA-256 HMAC for authentication, plus a
timestamp. `Fernet.encrypt`/`decrypt` are the only two operations `nebular.crypto` exposes
(`encrypt_value`/`decrypt_value`); no other module is meant to touch `cryptography` directly.

Because Fernet is *authenticated* encryption, a value can't just silently decrypt into garbage under
the wrong key — decrypting with the wrong key raises `InvalidToken` instead of returning corrupted
plaintext. That's what makes the startup canary check below effective.

## The startup canary

The very first time Nebular Vault boots against a fresh database, it encrypts a fixed string
(`"nebular-ok"`) and stores the ciphertext in a single-row table, `vault_meta`. Every subsequent
boot decrypts that same row and compares it back to `"nebular-ok"`.

If `NEBULAR_MASTER_KEY` has changed since the data was written — a typo, a lost secrets manager
entry, a copy-paste into the wrong environment — the canary check fails immediately at startup with
a clear error, and the app refuses to serve traffic. Without this check, a wrong key wouldn't
surface until the first time someone tried to reveal a value or the vault API tried to serve one,
at which point it would look like a confusing, unrelated 500 error deep in a request handler instead
of an obvious, actionable configuration problem.

## Key rotation — the one real limitation

**There is no key-rotation tool in this version.** If you change `NEBULAR_MASTER_KEY` after secrets
have already been stored, every previously encrypted value becomes permanently undecryptable — the
canary check will refuse to start the app rather than let you discover this one secret at a time.

If you genuinely need to rotate the master key, the only supported path today is:

1. With the *old* key still configured, reveal and copy out every secret value you need to keep
   (via the UI or `GET /api/v1/vault/secret`).
2. Stop the container, wipe the `vault_meta` row and every `secret_values` row (or start from a
   fresh `/data` volume entirely).
3. Start the container with the *new* `NEBULAR_MASTER_KEY`, recreate your Projects/Environments/Keys,
   and re-enter the values you saved in step 1.

A proper decrypt-under-old-key/re-encrypt-under-new-key migration tool is a reasonable future
addition, but doesn't exist yet — flagged here rather than left as a silent gap.

## What the master key does *not* protect against

Encryption at rest protects the data in the database file/backup from someone who gets a copy of it
without the key. It does **not** protect against:

- A compromised running container — anyone with access to a live session that can reveal values (an
  owner/admin account, or a valid project access key) can already read plaintext through the normal
  API, by design.
- A compromised `NEBULAR_MASTER_KEY` itself — treat it exactly like a database root password: inject
  it via your orchestrator's secret-injection mechanism, never bake it into an image or commit it to
  version control.
