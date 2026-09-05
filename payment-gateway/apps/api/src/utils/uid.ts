import crypto from 'crypto';
import { env } from '../config/env';

/**
 * Normalizes phone numbers to standard numeric strings (e.g. 01012345678)
 */
export function normalizePhone(phone: string): string {
  return phone.replace(/[^0-9]/g, '');
}

/**
 * Deterministic UID Generation Policy
 * 
 * WHY WE DO NOT SEND PII TO THE CHINESE SERVER:
 * 1. Compliance with the Korean Personal Information Protection Act (개인정보 보호법 제39조의11 - 국외 이전):
 *    Transferring PII (such as raw phone numbers, emails, real names, business numbers) out of South Korea
 *    requires explicit user consent, specific notifications (recipient, country, purpose, transfer method, etc.),
 *    and severe regulatory overhead. Sending a deterministic hash (UID) instead of raw PII eliminates the
 *    direct transfer of PII, significantly lowering security risk, regulatory complexity, and leakage impact.
 * 2. Immutable Identity Mapping:
 *    The UID acts as an immutable synthetic key. Even if a user updates their email or phone number in Korea, 
 *    their credit balance linked to the UID on the Chinese side remains unaffected.
 * 3. Security Boundary:
 *    If the Chinese server is compromised, no real identities (phone numbers, emails) are exposed.
 */
export function generateUID(params: {
  phone?: string;
  createdAtTimestamp: number;
  provider: string;
  providerSubject: string;
}): string {
  let seed = '';

  if (params.phone && params.phone.trim() !== '') {
    // Priority 1: Phone number available
    const normalized = normalizePhone(params.phone);
    // Add random nonce to prevent collisions for same phone + timestamp
    const nonce = crypto.randomBytes(8).toString('hex');
    seed = `${normalized}${params.createdAtTimestamp}${env.KOREA_SECRET_SALT_KEY}${nonce}`;
  } else {
    // Priority 2: Provider & Subject
    // Add random nonce to prevent collisions
    const nonce = crypto.randomBytes(8).toString('hex');
    seed = `${params.provider}${params.providerSubject}${env.KOREA_SECRET_SALT_KEY}${nonce}`;
  }

  return crypto
    .createHash('sha256')
    .update(seed)
    .digest('hex');
}

/**
 * Validates whether a UID is a valid 64-character SHA-256 hex string.
 */
export function isValidUID(uid: string): boolean {
  return /^[a-f0-9]{64}$/i.test(uid);
}
