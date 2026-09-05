import crypto from 'crypto';
import { env } from '../config/env';
import logger from './logger';

// Hashing with pepper key for searching/duplicate checks
export function sha256Hash(text: string | null | undefined): string | null {
  if (!text) return null;
  return crypto
    .createHmac('sha256', env.PII_HASH_PEPPER)
    .update(text.trim())
    .digest('hex');
}

// AES-256-GCM Encryption
export function encrypt(text: string | null | undefined): string | null {
  if (!text) return null;
  try {
    const key = Buffer.from(env.PII_ENCRYPTION_KEY, 'hex');
    const iv = crypto.randomBytes(12);
    const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);
    
    let encrypted = cipher.update(text, 'utf8', 'hex');
    encrypted += cipher.final('hex');
    
    const authTag = cipher.getAuthTag().toString('hex');
    // Format: iv_hex:ciphertext_hex:authtag_hex
    return `${iv.toString('hex')}:${encrypted}:${authTag}`;
  } catch (error) {
    // Log error but don't expose internal details
    logger.error('Encryption failed:', (error as Error).message);
    throw new Error('Encryption failed');
  }
}

// AES-256-GCM Decryption
export function decrypt(encryptedText: string | null | undefined): string | null {
  if (!encryptedText) return null;
  try {
    const parts = encryptedText.split(':');
    if (parts.length !== 3) {
      throw new Error('Invalid encrypted text format');
    }
    
    const iv = Buffer.from(parts[0], 'hex');
    const encrypted = Buffer.from(parts[1], 'hex');
    const authTag = Buffer.from(parts[2], 'hex');
    const key = Buffer.from(env.PII_ENCRYPTION_KEY, 'hex');
    
    const decipher = crypto.createDecipheriv('aes-256-gcm', key, iv);
    decipher.setAuthTag(authTag);
    
    let decrypted = decipher.update(encrypted as any, 'hex', 'utf8');
    decrypted += decipher.final('utf8');
    
    return decrypted;
  } catch (error) {
    // Log error but don't expose internal details
    logger.error('Decryption failed:', (error as Error).message);
    throw new Error('Decryption failed');
  }
}

// Masking Utilities
export function maskPhone(phone: string | null | undefined): string {
  if (!phone) return '';
  const cleaned = phone.replace(/[^0-9]/g, '');
  if (cleaned.length === 11) {
    // 01012345678 -> 010-****-5678
    return `${cleaned.slice(0, 3)}-****-${cleaned.slice(7)}`;
  } else if (cleaned.length === 10) {
    // 0212345678 -> 02-***-5678 or 031-***-5678
    const prefix = cleaned.startsWith('02') ? 2 : 3;
    const midLength = cleaned.length - prefix - 4;
    return `${cleaned.slice(0, prefix)}-${'*'.repeat(midLength)}-${cleaned.slice(cleaned.length - 4)}`;
  } else if (cleaned.length === 9) {
    // 021234567 -> 02-***-4567
    const prefix = cleaned.startsWith('02') ? 2 : 3;
    const midLength = cleaned.length - prefix - 4;
    return `${cleaned.slice(0, prefix)}-${'*'.repeat(midLength)}-${cleaned.slice(cleaned.length - 4)}`;
  }
  return '***-****-****';
}

export function maskEmail(email: string | null | undefined): string {
  if (!email) return '';
  const parts = email.split('@');
  if (parts.length !== 2) return '******';
  const name = parts[0];
  const domain = parts[1];
  if (name.length <= 2) {
    return `${name[0]}*@${domain}`;
  }
  const visibleCount = Math.min(3, Math.ceil(name.length / 2));
  const stars = '*'.repeat(name.length - visibleCount);
  return `${name.slice(0, visibleCount)}${stars}@${domain}`;
}

export function maskBusinessNumber(businessNumber: string | null | undefined): string {
  if (!businessNumber) return '';
  const cleaned = businessNumber.replace(/[^0-9]/g, '');
  if (cleaned.length === 10) {
    // 123-45-67890 -> 123-**-***90
    return `${cleaned.slice(0, 3)}-**-***${cleaned.slice(8)}`;
  }
  return '***-**-*****';
}

export function maskAccountNumber(accountNumber: string | null | undefined): string {
  if (!accountNumber) return '';
  // Mask all but last 4 digits
  const cleaned = accountNumber.replace(/[^0-9]/g, '');
  if (cleaned.length > 4) {
    const stars = '*'.repeat(cleaned.length - 4);
    return `${stars}-${cleaned.slice(cleaned.length - 4)}`;
  }
  return '****';
}

// Mask identity value based on type (phone, personal ID, or business registration number)
export function maskIdentityByType(value: string | null | undefined, identityType: string | null | undefined): string {
  if (!value) return '';
  if (identityType === 'PHONE') return maskPhone(value);
  if (identityType === 'BUSINESS_REG_NO') return maskBusinessNumber(value);
  // PERSONAL_ID or unknown: mask all but last 4 chars
  if (value.length > 4) {
    return '*'.repeat(value.length - 4) + value.slice(value.length - 4);
  }
  return '****';
}
