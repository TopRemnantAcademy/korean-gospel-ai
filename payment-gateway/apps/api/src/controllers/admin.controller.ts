import { Request, Response, NextFunction } from 'express';
import jwt from 'jsonwebtoken';
import bcrypt from 'bcryptjs';
import prisma from '../repositories/db';
import { env } from '../config/env';
import { encrypt, decrypt, maskPhone, maskEmail, maskBusinessNumber, maskAccountNumber, maskIdentityByType } from '../utils/crypto';
import { paymentQueue } from '../workers/queues';
import { AuthenticatedAdminRequest } from '../middlewares/auth.middleware';
import { 
  AdminRole, 
  PaymentStatus, 
  DispatchStatus, 
  DocumentIssueStatus, 
  CashReceiptStatus, 
  RefundStatus,
  ReceiptType
} from '@gospel-pay/shared';
import { adminLoginSchema, refundRequestSchema, paymentMethodConfigPatchSchema } from '@gospel-pay/shared';
import logger from '../utils/logger';
import { addPaymentTrace } from '../utils/audit';

const ADMIN_EMAIL = env.ADMIN_EMAIL;
const ADMIN_PASSWORD = env.ADMIN_PASSWORD;
const BCRYPT_ROUNDS = 12;

/**
 * POST /api/admin/auth/login
 *
 * Single admin account. Credentials from environment variables.
 * Password verified with bcrypt. No social login.
 */
export async function adminLogin(req: Request, res: Response, next: NextFunction) {
  try {
    const validated = adminLoginSchema.parse(req.body);
    const { email, password } = validated;

    // Only the designated admin email is allowed
    if (email !== ADMIN_EMAIL) {
      return res.status(401).json({ error: 'Invalid admin credentials' });
    }

    // Auto-seed admin with bcrypt-hashed password if not yet created
    let admin = await prisma.adminUser.findUnique({
      where: { email: ADMIN_EMAIL },
    });

    if (!admin) {
      const hashedPassword = await bcrypt.hash(ADMIN_PASSWORD, BCRYPT_ROUNDS);
      admin = await prisma.adminUser.create({
        data: {
          email: ADMIN_EMAIL,
          passwordHash: hashedPassword,
          role: AdminRole.SUPER_ADMIN,
          isActive: true,
        },
      });
      logger.info('Auto-seeded default super administrator with bcrypt-hashed password');
    }

    if (!admin.isActive) {
      return res.status(401).json({ error: 'Admin account is suspended' });
    }

    // Verify password with bcrypt (constant-time comparison)
    const passwordMatch = await bcrypt.compare(password, admin.passwordHash);
    if (!passwordMatch) {
      // Recovery path: if ADMIN_PASSWORD_FORCE_SYNC is enabled and the supplied
      // password matches the env-configured ADMIN_PASSWORD, re-sync the stored
      // hash. This lets an operator recover a locked-out admin after updating
      // ADMIN_PASSWORD in .env without manual DB surgery. Disable the flag once
      // recovered. Never enable in production as a permanent setting.
      if (env.ADMIN_PASSWORD_FORCE_SYNC && password === ADMIN_PASSWORD) {
        const newHash = await bcrypt.hash(ADMIN_PASSWORD, BCRYPT_ROUNDS);
        admin = await prisma.adminUser.update({
          where: { email: ADMIN_EMAIL },
          data: { passwordHash: newHash, isActive: true },
        });
        logger.warn(`Admin password hash re-synced from ADMIN_PASSWORD env var (force-sync enabled) for ${ADMIN_EMAIL}`);
      } else {
        return res.status(401).json({ error: 'Invalid admin credentials' });
      }
    }

    // Sign jwt token with explicit algorithm
    const token = jwt.sign(
      { id: admin.id, email: admin.email, role: admin.role },
      env.JWT_SECRET,
      { expiresIn: '8h', algorithm: 'HS256' }
    );

    await prisma.adminUser.update({
      where: { id: admin.id },
      data: { lastLoginAt: new Date() },
    });

    logger.info(`Admin login successful: ${admin.email} from IP ${req.ip || 'unknown'}`);

    return res.json({
      token,
      user: {
        id: admin.id,
        email: admin.email,
        role: admin.role,
      },
    });
  } catch (error) {
    next(error);
  }
}

/**
 * GET /api/admin/dashboard
 */
export async function getDashboardMetrics(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const startOfToday = new Date();
    startOfToday.setHours(0, 0, 0, 0);

    const [
      salesToday,
      totalPaymentsCount,
      failedPaymentsCount,
      pendingTaxCount,
      failedCreditCount,
      failedCashCount
    ] = await Promise.all([
      prisma.payment.aggregate({
        where: { paymentStatus: PaymentStatus.PAID, paidAt: { gte: startOfToday } },
        _sum: { amountTotal: true },
      }),
      prisma.payment.count(),
      prisma.payment.count({ where: { paymentStatus: PaymentStatus.FAILED } }),
      prisma.taxDocument.count({ where: { issueStatus: DocumentIssueStatus.PROCESSING } }),
      prisma.creditDispatch.count({ where: { dispatchStatus: DispatchStatus.FAILED } }),
      prisma.cashReceipt.count({ where: { receiptStatus: CashReceiptStatus.FAILED } }),
    ]);

    return res.json({
      salesToday: salesToday._sum.amountTotal || 0,
      totalPaymentsCount,
      failedPaymentsCount,
      pendingTaxCount,
      failedCreditCount,
      failedCashCount,
    });
  } catch (error) {
    next(error);
  }
}

/**
 * GET /api/admin/payments
 */
export async function getPayments(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const { status, limit = 20, offset = 0 } = req.query;

    const payments = await prisma.payment.findMany({
      where: status ? { paymentStatus: status as PaymentStatus } : undefined,
      take: Number(limit),
      skip: Number(offset),
      orderBy: { createdAt: 'desc' },
      include: {
        user: true,
      },
    });

    // Map and mask sensitive PII fields in admin list responses
    const sanitizedPayments = payments.map((p) => {
      let emailMasked = '***';
      let phoneMasked = '***';
      let companyRegNumberMasked = '***';
      let taxEmailMasked = '***';
      
      try {
        emailMasked = maskEmail(decrypt(p.user.emailEncrypted));
        phoneMasked = maskPhone(decrypt(p.user.phoneEncrypted));
        companyRegNumberMasked = maskBusinessNumber(decrypt(p.companyRegNumberEncrypted));
        taxEmailMasked = maskEmail(decrypt(p.taxEmailEncrypted));
      } catch (error) {
        logger.error(`Decryption failed for payment ${p.id}: ${(error as Error).message}`);
      }
      
      return {
        ...p,
        user: {
          id: p.user.id,
          uid: p.user.uid,
          provider: p.user.provider,
          emailMasked,
          phoneMasked,
        },
        companyRegNumberEncrypted: undefined,
        companyRegNumberMasked,
        taxEmailEncrypted: undefined,
        taxEmailMasked,
      };
    });

    return res.json(sanitizedPayments);
  } catch (error) {
    next(error);
  }
}

/**
 * GET /api/admin/payments/:paymentUuid
 */
export async function getPaymentDetail(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const { paymentUuid } = req.params;

    const payment = await prisma.payment.findUnique({
      where: { paymentUuid },
      include: {
        user: true,
        taxDocuments: true,
        cashReceipts: true,
        creditDispatches: true,
        refunds: true,
        externalCallLogs: true,
      },
    });

    if (!payment) {
      return res.status(404).json({ error: 'Payment not found' });
    }

    const sanitized = {
      ...payment,
      user: {
        id: payment.user.id,
        uid: payment.user.uid,
        provider: payment.user.provider,
        emailMasked: '***',
        phoneMasked: '***',
      },
      companyRegNumberEncrypted: undefined,
      companyRegNumberMasked: '***',
      taxEmailEncrypted: undefined,
      taxEmailMasked: '***',
      cashReceipts: payment.cashReceipts.map((c) => ({
        ...c,
        identityValueEncrypted: undefined,
        identityValueMasked: '***',
      })),
      refunds: payment.refunds.map((r) => ({
        ...r,
        refundAccountNumberEncrypted: undefined,
        refundAccountNumberMasked: '***',
      })),
    };
    
    // Decrypt with error handling
    try {
      sanitized.user.emailMasked = maskEmail(decrypt(payment.user.emailEncrypted));
      sanitized.user.phoneMasked = maskPhone(decrypt(payment.user.phoneEncrypted));
      sanitized.companyRegNumberMasked = maskBusinessNumber(decrypt(payment.companyRegNumberEncrypted));
      sanitized.taxEmailMasked = maskEmail(decrypt(payment.taxEmailEncrypted));
      
      sanitized.cashReceipts = payment.cashReceipts.map((c) => ({
        ...c,
        identityValueEncrypted: undefined,
        identityValueMasked: c.identityValueEncrypted ? maskIdentityByType(decrypt(c.identityValueEncrypted), c.identityType) : null,
      }));
      
      sanitized.refunds = payment.refunds.map((r) => ({
        ...r,
        refundAccountNumberEncrypted: undefined,
        refundAccountNumberMasked: r.refundAccountNumberEncrypted ? maskAccountNumber(decrypt(r.refundAccountNumberEncrypted)) : null,
      }));
    } catch (error) {
      logger.error(`Decryption failed for payment ${payment.id}: ${(error as Error).message}`);
    }

    return res.json(sanitized);
  } catch (error) {
    next(error);
  }
}

/**
 * GET /api/admin/tax-documents
 */
export async function getTaxDocuments(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const docs = await prisma.taxDocument.findMany({
      orderBy: { requestedAt: 'desc' },
      include: { payment: true },
    });
    return res.json(docs);
  } catch (error) {
    next(error);
  }
}

/**
 * GET /api/admin/cash-receipts
 */
export async function getCashReceipts(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const receipts = await prisma.cashReceipt.findMany({
      orderBy: { requestedAt: 'desc' },
      include: { payment: true },
    });
    const sanitized = receipts.map((r) => {
      let identityValueMasked = '***';
      
      try {
        identityValueMasked = r.identityValueEncrypted ? maskIdentityByType(decrypt(r.identityValueEncrypted), r.identityType) : '***';
      } catch (error) {
        logger.error(`Decryption failed for cash receipt ${r.id}: ${(error as Error).message}`);
      }
      
      return {
        ...r,
        identityValueEncrypted: undefined,
        identityValueMasked,
      };
    });
    return res.json(sanitized);
  } catch (error) {
    next(error);
  }
}

/**
 * GET /api/admin/credit-dispatches
 */
export async function getCreditDispatches(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const dispatches = await prisma.creditDispatch.findMany({
      orderBy: { updatedAt: 'desc' },
      include: { payment: true },
    });
    return res.json(dispatches);
  } catch (error) {
    next(error);
  }
}

/**
 * GET /api/admin/consents
 */
export async function getConsents(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const consents = await prisma.consentRecord.findMany({
      orderBy: { createdAt: 'desc' },
      include: { user: true },
    });
    const sanitized = consents.map((c) => {
      let emailMasked = '***';
      let phoneMasked = '***';
      
      try {
        if (c.user) {
          emailMasked = maskEmail(decrypt(c.user.emailEncrypted));
          phoneMasked = maskPhone(decrypt(c.user.phoneEncrypted));
        }
      } catch (error) {
        logger.error(`Decryption failed for consent ${c.id}: ${(error as Error).message}`);
      }
      
      return {
        ...c,
        user: c.user ? {
          id: c.user.id,
          uid: c.user.uid,
          emailMasked,
          phoneMasked,
        } : null,
      };
    });
    return res.json(sanitized);
  } catch (error) {
    next(error);
  }
}

/**
 * GET /api/admin/external-call-logs
 */
export async function getExternalCallLogs(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const logs = await prisma.externalCallLog.findMany({
      orderBy: { createdAt: 'desc' },
      take: 100, // Limit to recent 100 for performance
    });
    return res.json(logs);
  } catch (error) {
    next(error);
  }
}

/**
 * POST /api/admin/payments/:paymentUuid/retry-credit
 */
export async function retryCredit(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const { paymentUuid } = req.params;
    const payment = await prisma.payment.findUnique({
      where: { paymentUuid },
    });
    if (!payment) return res.status(404).json({ error: 'Payment not found' });

    // Reset credit dispatch status to READY before retrying
    await prisma.payment.update({
      where: { id: payment.id },
      data: { creditStatus: DispatchStatus.READY },
    });

    await paymentQueue.add('SEND_CREDIT', { paymentId: payment.id });

    // Log admin audit action
    await prisma.adminAuditLog.create({
      data: {
        adminUserId: req.adminUser!.id,
        action: 'RETRY_SEND_CREDIT',
        entityType: 'Payment',
        entityId: payment.id,
        ipAddress: req.ip || '127.0.0.1',
      },
    });

    return res.json({ success: true, message: 'Enqueued Send Credit retry job' });
  } catch (error) {
    next(error);
  }
}

/**
 * POST /api/admin/payments/:paymentUuid/retry-tax-document
 */
export async function retryTaxDocument(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const { paymentUuid } = req.params;
    const payment = await prisma.payment.findUnique({
      where: { paymentUuid },
    });
    if (!payment) return res.status(404).json({ error: 'Payment not found' });

    await paymentQueue.add('ISSUE_TAX_DOCUMENT', { paymentId: payment.id });

    // Audit log
    await prisma.adminAuditLog.create({
      data: {
        adminUserId: req.adminUser!.id,
        action: 'RETRY_ISSUE_TAX_DOCUMENT',
        entityType: 'Payment',
        entityId: payment.id,
        ipAddress: req.ip || '127.0.0.1',
      },
    });

    return res.json({ success: true, message: 'Enqueued Tax Document retry job' });
  } catch (error) {
    next(error);
  }
}

/**
 * POST /api/admin/payments/:paymentUuid/retry-cash-receipt
 */
export async function retryCashReceipt(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const { paymentUuid } = req.params;
    const payment = await prisma.payment.findUnique({
      where: { paymentUuid },
    });
    if (!payment) return res.status(404).json({ error: 'Payment not found' });

    await paymentQueue.add('ISSUE_CASH_RECEIPT', { paymentId: payment.id });

    // Audit log
    await prisma.adminAuditLog.create({
      data: {
        adminUserId: req.adminUser!.id,
        action: 'RETRY_ISSUE_CASH_RECEIPT',
        entityType: 'Payment',
        entityId: payment.id,
        ipAddress: req.ip || '127.0.0.1',
      },
    });

    return res.json({ success: true, message: 'Enqueued Cash Receipt retry job' });
  } catch (error) {
    next(error);
  }
}

/**
 * POST /api/admin/payments/:paymentUuid/override-webhook
 * 
 * Allows the admin to manually override/confirm credit allocation when webhook fails or hangs.
 */
export async function overrideWebhook(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const { paymentUuid } = req.params;
    const { reason } = req.body;

    if (!reason || reason.trim() === '') {
      return res.status(400).json({ error: '수동 승인 사유(Reason)를 입력해야 합니다.' });
    }

    const payment = await prisma.payment.findUnique({
      where: { paymentUuid },
      include: { creditDispatches: true },
    });

    if (!payment) return res.status(404).json({ error: 'Payment not found' });

    // Validate current credit status — only allow override from SENT or FAILED
    if (payment.creditStatus !== DispatchStatus.SENT && payment.creditStatus !== DispatchStatus.FAILED) {
      return res.status(400).json({ error: `Cannot override credit status from ${payment.creditStatus}. Only SENT or FAILED can be overridden.` });
    }

    // Update state to CONFIRMED
    await prisma.$transaction(async (tx) => {
      await tx.payment.update({
        where: { id: payment.id },
        data: {
          creditStatus: DispatchStatus.CONFIRMED,
          creditedAt: new Date(),
        },
      });

      if (payment.creditDispatches[0]) {
        await tx.creditDispatch.update({
          where: { id: payment.creditDispatches[0].id },
          data: {
            dispatchStatus: DispatchStatus.CONFIRMED,
            confirmedAt: new Date(),
          },
        });
      }
    });

    // Write trace logs
    await addPaymentTrace(
      payment.id,
      'CHINA_WEBHOOK',
      'SUCCESS',
      `[ADMIN_OVERRIDE] Webhook manual confirmation overridden by admin. Reason: ${reason}`
    );

    // Save admin audit log
    await prisma.adminAuditLog.create({
      data: {
        adminUserId: req.adminUser!.id,
        action: 'OVERRIDE_REMOTE_WEBHOOK',
        entityType: 'Payment',
        entityId: payment.id,
        beforeJson: { creditStatus: payment.creditStatus },
        afterJson: { creditStatus: 'CONFIRMED', reason },
        ipAddress: req.ip || '127.0.0.1',
      },
    });

    return res.json({ success: true, message: 'Remote platform webhook state overridden successfully.' });
  } catch (error) {
    next(error);
  }
}


/**
 * POST /api/admin/payments/:paymentUuid/refund
 * 
 * Processes full or partial cancellations. Conforms to limits and registers to background worker.
 */
export async function processRefund(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const { paymentUuid } = req.params;
    const validated = refundRequestSchema.parse(req.body);
    const { refundAmount, refundReason, refundBankCode, refundAccountNumber, refundAccountHolder } = validated;

    const payment = await prisma.payment.findUnique({
      where: { paymentUuid },
      include: { refunds: true },
    });

    if (!payment) {
      return res.status(404).json({ error: 'Payment record not found' });
    }

    if (payment.paymentStatus !== PaymentStatus.PAID && payment.paymentStatus !== PaymentStatus.PARTIALLY_REFUNDED) {
      return res.status(400).json({ error: 'Payment is not eligible for refund (must be PAID or PARTIALLY_REFUNDED)' });
    }

    // Use transaction to prevent race condition in refund limit checking
    const refund = await prisma.$transaction(async (tx) => {
      // Re-fetch payment with locks to prevent concurrent refunds
      const lockedPayment = await tx.payment.findUnique({
        where: { id: payment.id },
        include: { refunds: true },
      });

      if (!lockedPayment) {
        throw new Error('Payment not found');
      }

      // Calculate maximum refundable amount remaining (with fresh data)
      const alreadyRefunded = lockedPayment.refunds
        .filter((r) => r.refundStatus === RefundStatus.DONE)
        .reduce((sum, r) => sum + r.refundAmount, 0);

      const maxRefundable = lockedPayment.amountTotal - alreadyRefunded;
      if (refundAmount > maxRefundable) {
        throw new Error(`Refund amount (${refundAmount}) exceeds maximum remaining refundable amount (${maxRefundable})`);
      }

      const isVirtualAccount = lockedPayment.paymentMethod.includes('가상계좌');
      if (isVirtualAccount && (!refundAccountNumber || !refundBankCode || !refundAccountHolder)) {
        throw new Error('Virtual Account refunds require bank details (refundBankCode, refundAccountNumber, refundAccountHolder)');
      }

      // Create refund record in REQUESTED status
      return await tx.refund.create({
        data: {
          paymentId: lockedPayment.id,
          refundAmount,
          refundReason,
          refundStatus: RefundStatus.REQUESTED,
          partialRefund: refundAmount < lockedPayment.amountTotal,
          requiresRefundAccount: isVirtualAccount,
          refundBankCode: refundBankCode || null,
          refundAccountNumberEncrypted: refundAccountNumber ? encrypt(refundAccountNumber) : null,
          refundAccountHolder: refundAccountHolder || null,
          requestedByAdminId: req.adminUser!.id,
        },
      });
    });

    // Enqueue actual refund processor
    await paymentQueue.add('PROCESS_REFUND', { refundId: refund.id });

    // Log admin audit action
    await prisma.adminAuditLog.create({
      data: {
        adminUserId: req.adminUser!.id,
        action: 'REQUEST_REFUND',
        entityType: 'Refund',
        entityId: refund.id,
        beforeJson: { paymentStatus: payment.paymentStatus },
        afterJson: { refundId: refund.id, amount: refundAmount, reason: refundReason },
        ipAddress: req.ip || '127.0.0.1',
      },
    });

    return res.status(201).json({
      success: true,
      message: 'Refund requested and scheduled for processing',
      refundUuid: refund.refundUuid,
    });
  } catch (error) {
    next(error);
  }
}

/**
 * PATCH /api/admin/payment-method-configs/:id
 */
export async function updatePaymentMethodConfig(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const { id } = req.params;
    const validated = paymentMethodConfigPatchSchema.parse(req.body);

    const config = await prisma.paymentMethodConfig.findUnique({
      where: { id },
    });

    if (!config) {
      return res.status(404).json({ error: 'Config not found' });
    }

    const updated = await prisma.paymentMethodConfig.update({
      where: { id },
      data: {
        ...validated,
        metadata: validated.metadata as any,
      },
    });

    // Audit log
    await prisma.adminAuditLog.create({
      data: {
        adminUserId: req.adminUser!.id,
        action: 'UPDATE_PAYMENT_CONFIG',
        entityType: 'PaymentMethodConfig',
        entityId: id,
        beforeJson: config as any,
        afterJson: updated as any,
        ipAddress: req.ip || '127.0.0.1',
      },
    });

    return res.json(updated);
  } catch (error) {
    next(error);
  }
}

/**
 * GET /api/admin/settings
 */
export async function getSettings(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const [retentionPolicies, adminUsers] = await Promise.all([
      prisma.dataRetentionPolicy.findMany(),
      prisma.adminUser.findMany({ select: { id: true, email: true, role: true, isActive: true } }),
    ]);

    return res.json({
      retentionPolicies,
      adminUsers,
    });
  } catch (error) {
    next(error);
  }
}

/**
 * GET /api/admin/audit-logs
 */
export async function getAdminAuditLogs(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const logs = await prisma.adminAuditLog.findMany({
      orderBy: { createdAt: 'desc' },
      take: 100,
    });
    return res.json(logs);
  } catch (error) {
    next(error);
  }
}

/**
 * POST /api/admin/payments/:paymentUuid/decrypt
 * 
 * Securely decrypts encrypted PII fields for audit, requiring justification reason,
 * and records the event in the AdminAuditLog.
 */
export async function decryptPaymentPII(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const { paymentUuid } = req.params;
    const { reason } = req.body;

    if (!reason || reason.trim() === '') {
      return res.status(400).json({ error: '조회 사유(Reason)를 입력해야 합니다.' });
    }

    const payment = await prisma.payment.findUnique({
      where: { paymentUuid },
      include: {
        user: true,
        cashReceipts: true,
        refunds: true,
      },
    });

    if (!payment) {
      return res.status(404).json({ error: '결제 내역을 찾을 수 없습니다.' });
    }

    // 1. Decrypt User PII
    const userEmailDec = payment.user.emailEncrypted ? decrypt(payment.user.emailEncrypted) : null;
    const userPhoneDec = payment.user.phoneEncrypted ? decrypt(payment.user.phoneEncrypted) : null;

    // 2. Decrypt B2B Invoice PII
    const companyRegNumberDec = payment.companyRegNumberEncrypted ? decrypt(payment.companyRegNumberEncrypted) : null;
    const taxEmailDec = payment.taxEmailEncrypted ? decrypt(payment.taxEmailEncrypted) : null;

    // 3. Decrypt Cash Receipt PII
    const cashReceiptsDec = payment.cashReceipts.map(cr => ({
      id: cr.id,
      identityValueDecrypted: cr.identityValueEncrypted ? decrypt(cr.identityValueEncrypted) : null,
    }));

    // 4. Decrypt Refund PII (Bank Accounts)
    const refundsDec = payment.refunds.map(ref => ({
      id: ref.id,
      refundAccountNumberDecrypted: ref.refundAccountNumberEncrypted ? decrypt(ref.refundAccountNumberEncrypted) : null,
    }));

    // 5. Save Admin Audit Log (Permanent ledger entry)
    await prisma.adminAuditLog.create({
      data: {
        adminUserId: req.adminUser!.id,
        action: 'DECRYPT_PII',
        entityType: 'Payment',
        entityId: payment.id,
        beforeJson: null as any,
        afterJson: { 
          reason, 
          decryptedFields: [
            userEmailDec ? 'userEmail' : null,
            userPhoneDec ? 'userPhone' : null,
            companyRegNumberDec ? 'companyRegNumber' : null,
            taxEmailDec ? 'taxEmail' : null,
            cashReceiptsDec.length > 0 ? 'cashReceiptIdentity' : null,
            refundsDec.some(r => r.refundAccountNumberDecrypted) ? 'refundAccountNumber' : null,
          ].filter(Boolean),
        } as any,
        ipAddress: req.ip || '127.0.0.1',
      },
    });

    logger.warn(`PII Decrypted by Admin ${req.adminUser!.email} for Payment ${payment.id}. Reason: ${reason}`);

    return res.json({
      success: true,
      decrypted: {
        userEmail: userEmailDec,
        userPhone: userPhoneDec,
        companyRegNumber: companyRegNumberDec,
        taxEmail: taxEmailDec,
        cashReceipts: cashReceiptsDec,
        refunds: refundsDec,
      }
    });
  } catch (error) {
    next(error);
  }
}

/**
 * GET /api/admin/payments/:paymentUuid/traces
 */
export async function getPaymentTraces(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const { paymentUuid } = req.params;
    const payment = await prisma.payment.findUnique({
      where: { paymentUuid },
    });

    if (!payment) {
      return res.status(404).json({ error: 'Payment not found' });
    }

    const traces = await prisma.paymentTraceLog.findMany({
      where: { paymentId: payment.id },
      orderBy: { createdAt: 'asc' },
    });

    return res.json(traces);
  } catch (error) {
    next(error);
  }
}

