import { 
  encrypt, 
  decrypt, 
  sha256Hash, 
  maskPhone, 
  maskEmail, 
  maskBusinessNumber, 
  maskAccountNumber 
} from '../utils/crypto';

jest.mock('../config/env', () => ({
  env: {
    PII_ENCRYPTION_KEY: '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
    PII_HASH_PEPPER: 'pepper-salt-for-searching-hashed-pii-fields-12345',
  },
}));

describe('Cryptographic & Masking Services', () => {
  const rawText = '010-1234-5678';
  const emailText = 'piaoyhyh@gmail.com';
  const businessNumberText = '123-45-67890';
  const bankAccountText = '123-456-789012';

  test('encrypt and decrypt should be inverse functions', () => {
    const encrypted = encrypt(rawText);
    expect(encrypted).toBeDefined();
    expect(encrypted).not.toBe(rawText);

    const decrypted = decrypt(encrypted);
    expect(decrypted).toBe(rawText);
  });

  test('sha256Hash should be deterministic and output hex hashes', () => {
    const hash1 = sha256Hash(rawText);
    const hash2 = sha256Hash(rawText);
    expect(hash1).toBe(hash2);
    expect(hash1?.length).toBe(64);
  });

  test('maskPhone should mask middle numbers', () => {
    expect(maskPhone(rawText)).toBe('010-****-5678');
    expect(maskPhone('02-123-4567')).toBe('02-***-4567');
  });

  test('maskEmail should mask name parts', () => {
    expect(maskEmail(emailText)).toBe('pia*****@gmail.com');
    expect(maskEmail('ab@test.com')).toBe('a*@test.com');
  });

  test('maskBusinessNumber should mask middle sections', () => {
    expect(maskBusinessNumber(businessNumberText)).toBe('123-**-***90');
  });

  test('maskAccountNumber should mask all but last 4 digits', () => {
    expect(maskAccountNumber(bankAccountText)).toBe('********-9012');
  });
});
