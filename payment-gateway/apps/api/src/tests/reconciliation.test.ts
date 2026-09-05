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

const dbMock: any = {
  remittance: {
    create: jest.fn(),
    findUnique: jest.fn(),
    findMany: jest.fn(),
  },
  reconciliationLog: {
    create: jest.fn(),
    update: jest.fn(),
    findUnique: jest.fn(),
    findFirst: jest.fn(),
    findMany: jest.fn(),
  },
  payment: {
    findMany: jest.fn(),
    update: jest.fn(),
    findUnique: jest.fn(),
  },
  paymentTraceLog: {
    create: jest.fn(),
    findMany: jest.fn(),
  },
  creditDispatch: {
    update: jest.fn(),
  },
  adminAuditLog: {
    create: jest.fn(),
  },
  $transaction: jest.fn((callback) => callback(dbMock)),
};

jest.mock('../repositories/db', () => ({
  __esModule: true,
  default: dbMock,
}));

import { importRemittances, runReconciliation } from '../controllers/reconciliation.controller';
import { getPaymentTraces, overrideWebhook } from '../controllers/admin.controller';
import { handleRemoteWebhook } from '../controllers/payment.controller';
import { addPaymentTrace } from '../utils/audit';
import prisma from '../repositories/db';
import { Request, Response } from 'express';

describe('3-Way Reconciliation & Audit Tracing Tests', () => {
  let mockRequest: Partial<Request>;
  let mockResponse: Partial<Response>;
  let nextFunction: jest.Mock;

  beforeEach(() => {
    mockRequest = {};
    mockResponse = {
      status: jest.fn().mockReturnThis(),
      json: jest.fn(),
      send: jest.fn(),
      setHeader: jest.fn(),
    };
    nextFunction = jest.fn();
    jest.clearAllMocks();
  });

  describe('CSV Remittance Statement Import', () => {
    test('should parse CSV lines and skip existing keys', async () => {
      mockRequest.body = {
        csvData: `date,remittanceKey,bankName,amountUsd,exchangeRate,feeUsd,feeKrw,justification\n2026-05-15,REMIT-001,Hana Bank,11000.00,1385.50,50.00,69275,Wire for settlement`
      };

      (prisma.remittance.findUnique as jest.Mock).mockResolvedValue(null);
      (prisma.remittance.create as jest.Mock).mockResolvedValue({});

      await importRemittances(mockRequest as Request, mockResponse as Response, nextFunction);

      expect(prisma.remittance.create).toHaveBeenCalledWith(expect.objectContaining({
        data: expect.objectContaining({
          remittanceKey: 'REMIT-001',
          amountKrw: 15240500, // 11000 * 1385.5 = 15240500
          feeKrw: 69275,
        })
      }));
      expect(mockResponse.status).toHaveBeenCalledWith(201);
    });
  });

  describe('3-Way Reconciliation Engine', () => {
    test('should run monthly reconciliation and compute exchange loss variance correctly', async () => {
      mockRequest.body = { month: '2026-05' };

      // Mock remittances total: 11,000 USD @ 1385.5 = 15,240,500 KRW, fee: 69,275 KRW
      (prisma.remittance.findMany as jest.Mock).mockResolvedValue([
        {
          id: 'remit-1',
          amountKrw: 15240500,
          amountUsd: 11000.00,
          exchangeRate: 1385.5,
          feeKrw: 69275,
        }
      ]);

      // Mock PG collections: 15,100,000 KRW (leads to discrepancy: 15,100,000 - 15,240,500 = -140,500 KRW)
      // Since fee is 69,275, fxLoss = 140,500 - 69,275 = 71,225 KRW
      (prisma.payment.findMany as jest.Mock).mockResolvedValue([
        {
          id: 'p-1',
          amountTotal: 15100000,
          amountSupply: 13727273,
          amountVat: 1372727,
          taxDocuments: [
            {
              issueStatus: 'SENT',
            }
          ]
        }
      ]);

      (prisma.payment.update as jest.Mock).mockResolvedValue({});
      (prisma.reconciliationLog.findUnique as jest.Mock).mockResolvedValue(null);
      (prisma.reconciliationLog.create as jest.Mock).mockImplementation((args) => Promise.resolve(args.data));

      await runReconciliation(mockRequest as Request, mockResponse as Response, nextFunction);

      expect(prisma.reconciliationLog.create).toHaveBeenCalledWith(expect.objectContaining({
        data: expect.objectContaining({
          targetMonth: '2026-05',
          totalPgAmountKrw: 15100000,
          totalRemittanceKrw: 15240500,
          varianceAmountKrw: -140500,
          feeVarianceKrw: 69275,
          fxLossKrw: 71225, // Math.abs(-140500) - 69275 = 71225
          fxGainKrw: 0,
        })
      }));
    });

    test('should compute exchange gain variance correctly when collections exceed remittances', async () => {
      mockRequest.body = { month: '2026-06' };

      // Mock remittances total: 8,500 USD @ 1392.2 = 11,833,700 KRW, fee: 55,688 KRW
      (prisma.remittance.findMany as jest.Mock).mockResolvedValue([
        {
          id: 'remit-2',
          amountKrw: 11833700,
          amountUsd: 8500.00,
          exchangeRate: 1392.2,
          feeKrw: 55688,
        }
      ]);

      // Mock PG collections: 12,000,000 KRW (leads to gain: 12,000,000 - 11,833,700 = +166,300 KRW)
      (prisma.payment.findMany as jest.Mock).mockResolvedValue([
        {
          id: 'p-2',
          amountTotal: 12000000,
          amountSupply: 10909091,
          amountVat: 1090909,
          taxDocuments: [
            {
              issueStatus: 'SENT',
            }
          ]
        }
      ]);

      (prisma.payment.update as jest.Mock).mockResolvedValue({});
      (prisma.reconciliationLog.findUnique as jest.Mock).mockResolvedValue(null);
      (prisma.reconciliationLog.create as jest.Mock).mockImplementation((args) => Promise.resolve(args.data));

      await runReconciliation(mockRequest as Request, mockResponse as Response, nextFunction);

      expect(prisma.reconciliationLog.create).toHaveBeenCalledWith(expect.objectContaining({
        data: expect.objectContaining({
          targetMonth: '2026-06',
          totalPgAmountKrw: 12000000,
          totalRemittanceKrw: 11833700,
          varianceAmountKrw: 166300,
          fxLossKrw: 0,
          fxGainKrw: 166300,
        })
      }));
    });
  });

  describe('Payment Audit Tracing Log', () => {
    test('addPaymentTrace should create a trace record in DB', async () => {
      (prisma.paymentTraceLog.create as jest.Mock).mockResolvedValue({ id: 'trace-1' });

      await addPaymentTrace('p-100', 'PG_PAYMENT', 'SUCCESS', 'Payment confirmation completed');

      expect(prisma.paymentTraceLog.create).toHaveBeenCalledWith(expect.objectContaining({
        data: expect.objectContaining({
          paymentId: 'p-100',
          stage: 'PG_PAYMENT',
          status: 'SUCCESS',
          message: 'Payment confirmation completed',
        })
      }));
    });

    test('getPaymentTraces controller should fetch traces for a specific payment', async () => {
      mockRequest.params = { paymentUuid: 'pay-uuid-abc' };
      (prisma.payment.findUnique as jest.Mock).mockResolvedValue({ id: 'p-100' });
      (prisma.paymentTraceLog.findMany as jest.Mock).mockResolvedValue([
        { id: 'trace-1', stage: 'PG_PAYMENT', status: 'SUCCESS' }
      ]);

      await getPaymentTraces(mockRequest as Request, mockResponse as Response, nextFunction);

      expect(prisma.paymentTraceLog.findMany).toHaveBeenCalledWith(expect.objectContaining({
        where: { paymentId: 'p-100' }
      }));
      expect(mockResponse.json).toHaveBeenCalledWith(expect.arrayContaining([
        expect.objectContaining({ id: 'trace-1' })
      ]));
    });
  });

  describe('Remote Webhook Callback & Admin Override', () => {
    const testSecretKey = 'dummy_china_credit_api_key';

    test('handleRemoteWebhook should reject invalid signatures', async () => {
      mockRequest.body = {
        paymentUuid: 'pay-uuid-123',
        status: 'SUCCESS',
        signature: 'invalid_sig'
      };

      await handleRemoteWebhook(mockRequest as Request, mockResponse as Response, nextFunction);

      expect(mockResponse.status).toHaveBeenCalledWith(401);
      expect(mockResponse.json).toHaveBeenCalledWith({ error: 'Invalid webhook signature' });
    });

    test('handleRemoteWebhook should process successful callback and transition state to CONFIRMED', async () => {
      const paymentUuid = 'pay-uuid-123';
      const status = 'SUCCESS';
      
      const hmac = require('crypto').createHmac('sha256', testSecretKey);
      const signature = hmac.update(paymentUuid + status).digest('hex');

      mockRequest.body = { paymentUuid, status, signature };

      (prisma.payment.findUnique as jest.Mock).mockResolvedValue({
        id: 'p-123',
        paymentUuid,
        creditStatus: 'SENT',
        creditDispatches: [{ id: 'cd-123' }],
      });

      await handleRemoteWebhook(mockRequest as Request, mockResponse as Response, nextFunction);

      expect(prisma.payment.update).toHaveBeenCalledWith(expect.objectContaining({
        where: { id: 'p-123' },
        data: expect.objectContaining({
          creditStatus: 'CONFIRMED',
        })
      }));
      expect(mockResponse.json).toHaveBeenCalledWith({ success: true });
    });

    test('overrideWebhook should update payment and dispatch state with justification reason', async () => {
      mockRequest.params = { paymentUuid: 'pay-uuid-123' };
      mockRequest.body = { reason: 'Confirmed manually via phone call' };
      (mockRequest as any).adminUser = { id: 'admin-123', email: 'admin@worksite.example.com', role: 'SUPER_ADMIN' } as any;

      (prisma.payment.findUnique as jest.Mock).mockResolvedValue({
        id: 'p-123',
        creditStatus: 'SENT',
        creditDispatches: [{ id: 'cd-123' }],
      });

      await overrideWebhook(mockRequest as Request, mockResponse as Response, nextFunction);

      expect(prisma.payment.update).toHaveBeenCalledWith(expect.objectContaining({
        where: { id: 'p-123' },
        data: expect.objectContaining({
          creditStatus: 'CONFIRMED',
        })
      }));
      expect(prisma.adminAuditLog.create).toHaveBeenCalledWith(expect.objectContaining({
        data: expect.objectContaining({
          adminUserId: 'admin-123',
          action: 'OVERRIDE_REMOTE_WEBHOOK',
        })
      }));
      expect(mockResponse.json).toHaveBeenCalledWith(expect.objectContaining({
        success: true,
        message: expect.stringContaining('overridden successfully')
      }));
    });
  });
});
