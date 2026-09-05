import dotenv from 'dotenv';
import path from 'path';
import { z } from 'zod';

// Load environment variables
dotenv.config({ path: path.resolve(__dirname, '../../../../.env') });

const envSchema = z.object({
  PORT: z.coerce.number().default(5000),
  NODE_ENV: z.enum(['development', 'production', 'test']).default('production'),
  DATABASE_URL: z.string().url(),
  REDIS_URL: z.string().url().default('redis://localhost:6379'),
  JWT_SECRET: z.string().min(32),
  KOREA_SECRET_SALT_KEY: z.string().min(32),
  PII_ENCRYPTION_KEY: z.string().length(64).regex(/^[0-9a-f]{64}$/, 'Must be 64 hex chars (cryptographically random)'),
  PII_HASH_PEPPER: z.string().min(32),
  SSO_JWT_SECRET: z.string().min(32),
  SSO_REDIRECT_ALLOWLIST: z.string().transform((val) => val.split(',')),
  PG_API_SECRET_KEY: z.string().min(16),
  TAX_INVOICE_API_KEY: z.string().min(16),
  CHINA_CREDIT_API_URL: z.string().url(),
  CHINA_CREDIT_API_KEY: z.string().min(16),
  MOCK_CHINA_API: z.coerce.boolean().default(false),
  CORS_ORIGINS: z.string().transform((val) => val.split(',').map(s => s.trim()).filter(Boolean)).default('http://localhost:5173,http://localhost:5174'),
  ADMIN_EMAIL: z.string().email().default('piaoyhyh@gmail.com'),
  ADMIN_PASSWORD: z.string().min(8).default('qkrdid99GNS!'),
  // When true, a failed admin login that matches ADMIN_PASSWORD from env will
  // re-sync (overwrite) the stored bcrypt hash. Use to recover a locked-out admin
  // after changing ADMIN_PASSWORD in .env. Disable in production once recovered.
  ADMIN_PASSWORD_FORCE_SYNC: z.coerce.boolean().default(false),
  BACKUP_DIR: z.string().default('./backups'),
});

const parsed = envSchema.safeParse(process.env);

if (!parsed.success) {
  console.error('Invalid Environment Configuration:', JSON.stringify(parsed.error.format(), null, 2));
  process.exit(1);
}

// Reject known weak/default secrets in production
if (parsed.data.NODE_ENV === 'production') {
  const weakSecrets = [
    'super-secret-korean-payment-admin-jwt-token-key-12345',
    '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
    'stable-salt-key-for-uid-generation-korea-server-side',
    'pepper-salt-for-searching-hashed-pii-fields-12345',
    'china-sso-verification-shared-jwt-secret-key-98765',
  ];
  const allSecrets = [
    parsed.data.JWT_SECRET,
    parsed.data.PII_ENCRYPTION_KEY,
    parsed.data.PII_HASH_PEPPER,
    parsed.data.SSO_JWT_SECRET,
    parsed.data.KOREA_SECRET_SALT_KEY,
    parsed.data.PG_API_SECRET_KEY,
    parsed.data.CHINA_CREDIT_API_KEY,
  ];
  for (const secret of allSecrets) {
    if (weakSecrets.includes(secret)) {
      console.error(`FATAL: Known default/weak secret detected in production. Generate a new cryptographically random secret.`);
      process.exit(1);
    }
  }

  // Reject default admin password in production
  if (parsed.data.ADMIN_PASSWORD === 'qkrdid99GNS!') {
    console.error('FATAL: Default admin password detected in production. Set ADMIN_PASSWORD environment variable to a strong password.');
    process.exit(1);
  }
}

export const env = parsed.data;
