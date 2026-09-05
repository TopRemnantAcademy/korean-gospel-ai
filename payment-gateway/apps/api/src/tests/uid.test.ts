import { generateUID, isValidUID, normalizePhone } from '../utils/uid';
import { env } from '../config/env';

// Mock env parameters for stable testing
jest.mock('../config/env', () => ({
  env: {
    KOREA_SECRET_SALT_KEY: 'stable-salt-key-for-uid-generation-korea-server-side',
  },
}));

describe('UID Generation Policy & Validation', () => {
  const phone = '010-1234-5678';
  const timestamp = 1718000000000;
  const provider = 'google';
  const providerSubject = 'subject_123456';

  test('normalizePhone should strip spaces and hyphens', () => {
    expect(normalizePhone('010-1234-5678')).toBe('01012345678');
    expect(normalizePhone(' 010 1234 5678 ')).toBe('01012345678');
  });

  test('Priority 1: generateUID with phone should result in phone-based deterministic hash', () => {
    const uid = generateUID({
      phone,
      createdAtTimestamp: timestamp,
      provider,
      providerSubject,
    });

    expect(uid).toBeDefined();
    expect(uid.length).toBe(64);
    expect(isValidUID(uid)).toBe(true);

    // Re-generating with identical parameters must yield identical hash (idempotent)
    const uid2 = generateUID({
      phone,
      createdAtTimestamp: timestamp,
      provider,
      providerSubject,
    });
    expect(uid).toBe(uid2);
  });

  test('Priority 2: generateUID without phone should use provider and subject ID', () => {
    const uid = generateUID({
      createdAtTimestamp: timestamp,
      provider,
      providerSubject,
    });

    expect(uid).toBeDefined();
    expect(uid.length).toBe(64);
    expect(isValidUID(uid)).toBe(true);

    const uid2 = generateUID({
      createdAtTimestamp: timestamp,
      provider,
      providerSubject,
    });
    expect(uid).toBe(uid2);
  });

  test('generateUID should output different values for different timestamps', () => {
    const uid1 = generateUID({
      phone,
      createdAtTimestamp: timestamp,
      provider,
      providerSubject,
    });

    const uid2 = generateUID({
      phone,
      createdAtTimestamp: timestamp + 1,
      provider,
      providerSubject,
    });

    expect(uid1).not.toBe(uid2);
  });

  test('isValidUID should validate hex strings', () => {
    expect(isValidUID('0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef')).toBe(true);
    expect(isValidUID('invalid-uid-length')).toBe(false);
    expect(isValidUID('0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdeg')).toBe(false); // non-hex
  });
});
