// Mock env variables before importing anything to avoid validation issues
jest.mock('../config/env', () => ({
  env: {
    DATABASE_URL: 'postgresql://dummy:dummy@localhost:5432/dummy',
    REDIS_URL: 'redis://localhost:6379',
    JWT_SECRET: 'dummy_jwt_secret_key_long_enough',
    KOREA_SECRET_SALT_KEY: 'stable-salt-key-for-uid-generation-korea-server-side',
    PII_ENCRYPTION_KEY: '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
    PII_HASH_PEPPER: 'dummy_hash_pepper_value',
    SSO_JWT_SECRET: 'dummy_sso_jwt_secret_key_long_enough',
    SSO_REDIRECT_ALLOWLIST: ['https://allow.example.com'],
    PG_API_SECRET_KEY: 'dummy_pg_api_secret_key',
    TAX_INVOICE_API_KEY: 'dummy_tax_invoice_api_key',
    CHINA_CREDIT_API_URL: 'https://china.example.com',
    CHINA_CREDIT_API_KEY: 'dummy_china_credit_api_key',
  },
}));

jest.mock('../repositories/db', () => ({
  __esModule: true,
  default: {
    user: {
      findFirst: jest.fn(),
      findUnique: jest.fn(),
      create: jest.fn(),
      update: jest.fn(),
      findMany: jest.fn(),
    },
    consentRecord: {
      create: jest.fn(),
    },
    payment: {
      findMany: jest.fn(),
      update: jest.fn(),
    },
    adminAuditLog: {
      create: jest.fn(),
    },
    dataRetentionPolicy: {
      findMany: jest.fn(),
    },
    paymentOrder: {
      updateMany: jest.fn(),
    },
  },
}));

import { isLocalIp } from '../utils/ip';
import { socialIdentify } from '../controllers/auth.controller';
import { handleDataRetentionCleanup } from '../workers/workers';
import prisma from '../repositories/db';
import { Request, Response } from 'express';
import { Job } from 'bullmq';

describe('Data Retention & Local IP Policy Tests', () => {
  let mockRequest: Partial<Request>;
  let mockResponse: Partial<Response>;
  let nextFunction: jest.Mock;

  beforeEach(() => {
    mockRequest = { headers: {} };
    mockResponse = {
      status: jest.fn().mockReturnThis(),
      json: jest.fn(),
    };
    nextFunction = jest.fn();
    (prisma.paymentOrder.updateMany as jest.Mock).mockResolvedValue({ count: 0 });
    (prisma.adminAuditLog.create as jest.Mock).mockResolvedValue({});
    (prisma.user.update as jest.Mock).mockResolvedValue({});
    (prisma.payment.update as jest.Mock).mockResolvedValue({});
    jest.clearAllMocks();
  });

  describe('isLocalIp Utility', () => {
    test('should identify loopback and local development IPs', () => {
      expect(isLocalIp('127.0.0.1')).toBe(true);
      expect(isLocalIp('::1')).toBe(true);
      expect(isLocalIp('localhost')).toBe(true);
      expect(isLocalIp('::ffff:127.0.0.1')).toBe(true);
    });

    test('should identify private RFC 1918 networks', () => {
      expect(isLocalIp('10.0.0.1')).toBe(true);
      expect(isLocalIp('192.168.1.10')).toBe(true);
      expect(isLocalIp('172.16.0.1')).toBe(true);
      expect(isLocalIp('172.31.255.255')).toBe(true);
      expect(isLocalIp('172.32.0.1')).toBe(false); // Out of private range
    });

    test('should identify designated domestic/local IP ranges', () => {
      expect(isLocalIp('121.254.100.1')).toBe(true);
      expect(isLocalIp('210.89.23.4')).toBe(true);
      expect(isLocalIp('211.233.1.5')).toBe(true);
      expect(isLocalIp('14.52.12.3')).toBe(true);
      expect(isLocalIp('218.156.4.5')).toBe(true);
    });

    test('should identify remote/external IPs as false', () => {
      expect(isLocalIp('8.8.8.8')).toBe(false);
      expect(isLocalIp('104.244.42.1')).toBe(false);
      expect(isLocalIp(null)).toBe(false);
      expect(isLocalIp(undefined)).toBe(false);
    });
  });

  describe('socialIdentify IP Capture', () => {
    test('should capture req.ip and save it as registeredIp when registering new user', async () => {
      mockRequest.body = {
        provider: 'google',
        providerSubject: 'sub123',
        email: 'user@example.com',
        phone: '010-1234-5678',
      };
      Object.defineProperty(mockRequest, 'ip', { value: '121.254.100.1', writable: true });

      (prisma.user.findFirst as jest.Mock).mockResolvedValue(null);
      (prisma.user.create as jest.Mock).mockImplementation((args) => Promise.resolve({
        id: 'user-uuid-123',
        uid: 'user-uid-123',
        registeredIp: args.data.registeredIp,
      }));

      await socialIdentify(mockRequest as Request, mockResponse as Response, nextFunction);

      if (nextFunction.mock.calls.length > 0) {
        console.error("socialIdentify error:", nextFunction.mock.calls[0][0]);
      }

      expect(prisma.user.create).toHaveBeenCalledWith(expect.objectContaining({
        data: expect.objectContaining({
          registeredIp: '121.254.100.1',
        })
      }));
      expect(mockResponse.status).toHaveBeenCalledWith(201);
    });
  });

  describe('Data Retention Worker Deletion Bypass', () => {
    test('should bypass PII deletion for deleted users registered with local IP', async () => {
      // Mock two policies
      (prisma.dataRetentionPolicy.findMany as jest.Mock).mockResolvedValue([
        { dataCategory: 'PII_DELETED_USERS', retentionDays: 30, isActive: true },
      ]);

      // Mock users: one local IP, one remote IP
      (prisma.user.findMany as jest.Mock).mockResolvedValue([
        {
          id: 'local-user',
          uid: 'uid-local',
          emailEncrypted: 'email1',
          registeredIp: '210.89.23.4', // Local IP
        },
        {
          id: 'remote-user',
          uid: 'uid-remote',
          emailEncrypted: 'email2',
          registeredIp: '8.8.8.8', // Remote IP
        }
      ]);

      const mockJob = { id: 'job-1', name: 'DATA_RETENTION_CLEANUP', data: {} } as unknown as Job;

      await handleDataRetentionCleanup(mockJob);

      // Verify user.update was NOT called for local-user, but was called for remote-user
      expect(prisma.user.update).not.toHaveBeenCalledWith(expect.objectContaining({
        where: { id: 'local-user' }
      }));

      expect(prisma.user.update).toHaveBeenCalledWith(expect.objectContaining({
        where: { id: 'remote-user' },
        data: expect.objectContaining({
          emailEncrypted: null,
        })
      }));
    });

    test('should bypass payment payload masking for payments of local IP users', async () => {
      (prisma.dataRetentionPolicy.findMany as jest.Mock).mockResolvedValue([
        { dataCategory: 'PAYMENT_RAW_PAYLOADS', retentionDays: 1825, isActive: true },
      ]);

      // Mock payments: one linked to local IP user, one to remote IP user
      (prisma.payment.findMany as jest.Mock).mockResolvedValue([
        {
          id: 'local-payment',
          paymentUuid: 'p-uuid-local',
          user: { registeredIp: '121.254.100.1' }, // Local IP user
        },
        {
          id: 'remote-payment',
          paymentUuid: 'p-uuid-remote',
          user: { registeredIp: '104.244.42.1' }, // Remote IP user
        }
      ]);

      const mockJob = { id: 'job-2', name: 'DATA_RETENTION_CLEANUP', data: {} } as unknown as Job;

      await handleDataRetentionCleanup(mockJob);

      // Verify payment.update was NOT called for local-payment, but was called for remote-payment
      expect(prisma.payment.update).not.toHaveBeenCalledWith(expect.objectContaining({
        where: { id: 'local-payment' }
      }));

      expect(prisma.payment.update).toHaveBeenCalledWith(expect.objectContaining({
        where: { id: 'remote-payment' },
        data: expect.objectContaining({
          rawPgPayload: null,
        })
      }));
    });
  });
});
