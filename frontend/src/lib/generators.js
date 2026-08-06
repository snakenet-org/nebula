// @ai-purpose: Client-side UUID v4 / secure password generation for the header's password generator.
// @ai-context: Both use Web Crypto (crypto.randomUUID / crypto.getRandomValues), never Math.random —
//   this is meant to produce values a caller may actually use as a credential. generateSecurePassword
//   rejection-samples each byte against the largest multiple of the charset length that fits in a
//   byte (248 for a 62-char charset, i.e. multiples of the charset length up to 256), discarding any
//   byte >= that bound before taking it mod charset.length — without this, `byte % charsetLength`
//   would be measurably biased toward the low end of the charset for any charset length that doesn't
//   evenly divide 256.
// @version: 1.0.0
// @author: Marc Fiedler <marc@snakenet.org>
// @date: 2026-08-06

export const PASSWORD_MIN_LENGTH = 10;
export const PASSWORD_MAX_LENGTH = 25;

const PASSWORD_CHARSET =
  'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-';

export function generateUuidV4() {
  return crypto.randomUUID();
}

export function generateSecurePassword(length) {
  const charsetLength = PASSWORD_CHARSET.length;
  const rejectionBound = Math.floor(256 / charsetLength) * charsetLength;
  const bytes = new Uint8Array(1);
  let result = '';
  while (result.length < length) {
    crypto.getRandomValues(bytes);
    if (bytes[0] >= rejectionBound) continue;
    result += PASSWORD_CHARSET[bytes[0] % charsetLength];
  }
  return result;
}
