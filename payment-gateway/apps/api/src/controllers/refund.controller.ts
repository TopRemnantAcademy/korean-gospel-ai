import { Response, NextFunction } from 'express';
import prisma from '../repositories/db';
import { paymentQueue } from '../workers/queues';
import { AuthenticatedAdminRequest } from '../middlewares/auth.middleware';
import logger from '../utils/logger';
import { z } from 'zod';

const refundRequestSchema = z.object({
  amount: z.number().int().positive().optional(), // If not provided, full refund
  reason: z.string().min(5).max(500),
  reasonCode: z.enum(['CUSTOMER_REQUEST', 'DUPLICATE_PAYMENT', 'FRAUD', 'SYSTEM_ERROR', 'OTHER']),
});

/**
 * GET /api/admin/v2/refunds
 * Get list of refund requests
 */
export async function getRefunds(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const { status, page = '1', limit = '20' } = req.query;
    const pageNum = parseInt(page as string, 10);
    const limitNum = parseInt(limit as string, 10);
    const skip = (pageNum - 1) * limitNum;

    const where: any = {};
    if (status) {
      where.refundStatus = status;
    }

    const [refunds, total] = await Promise.all([
      prisma.refund.findMany({
        where,
        include: {
          payment: {
            select: {
              id: true,
              amountTotal: true,
              paymentStatus: true,
              paymentMethod: true,
              createdAt: true,
            },
          },
        },
        orderBy: { createdAt: 'desc' },
        skip,
        take: limitNum,
      }),
      prisma.refund.count({ where }),
    ]);

    return res.json({
      refunds,
      pagination: {
        page: pageNum,
        limit: limitNum,
        total,
        totalPages: Math.ceil(total / limitNum),
      },
    });
  } catch (error) {
    next(error);
  }
}

/**
 * GET /api/admin/v2/payments/:id/refund-info
 * Get refund information for a payment
 */
export async function getPaymentRefundInfo(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const { id } = req.params;

    const payment = await prisma.payment.findUnique({
      where: { id },
      include: {
        refunds: {
          orderBy: { createdAt: 'desc' },
        },
      },
    });

    if (!payment) {
      return res.status(404).json({ error: 'Payment not found' });
    }

    // Calculate total refunded amount
    const totalRefunded = payment.refunds
      .filter(r => r.refundStatus === 'DONE')
      .reduce((sum, r) => sum + r.refundAmount, 0);

    const refundInfo = {
      paymentId: payment.id,
      paymentAmount: payment.amountTotal,
      totalRefunded,
      refundableAmount: payment.amountTotal - totalRefunded,
      refunds: payment.refunds,
      canRefund: (payment.paymentStatus === 'PAID' || payment.paymentStatus === 'PARTIALLY_REFUNDED') && (payment.amountTotal - totalRefunded) > 0,
    };

    return res.json(refundInfo);
  } catch (error) {
    next(error);
  }
}

/**
 * POST /api/admin/v2/payments/:id/refund
 * Process refund for a payment
 */
export async function processRefund(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const { id } = req.params;
    const validated = refundRequestSchema.parse(req.body);

    const payment = await prisma.payment.findUnique({
      where: { id },
    });

    if (!payment) {
      return res.status(404).json({ error: 'Payment not found' });
    }

    if (payment.paymentStatus !== 'PAID' && payment.paymentStatus !== 'PARTIALLY_REFUNDED') {
      return res.status(400).json({ error: 'Payment is not eligible for refund (must be PAID or PARTIALLY_REFUNDED)' });
    }

    // Use transaction to prevent race condition in refund limit checking
    const refund = await prisma.$transaction(async (tx) => {
      // Re-fetch payment with locks to prevent concurrent refunds
      const lockedPayment = await tx.payment.findUnique({
        where: { id },
        include: { refunds: true },
      });

      if (!lockedPayment) {
        throw new Error('Payment not found');
      }

      // Calculate maximum refundable amount remaining (with fresh data)
      const totalRefunded = lockedPayment.refunds
        .filter(r => r.refundStatus === 'DONE')
        .reduce((sum, r) => sum + r.refundAmount, 0);

      const maxRefundable = lockedPayment.amountTotal - totalRefunded;
      const refundAmount = validated.amount || maxRefundable;

      if (refundAmount <= 0) {
        throw new Error('Refund amount must be greater than 0');
      }

      if (refundAmount > maxRefundable) {
        throw new Error(`Refund amount (${refundAmount}) exceeds maximum remaining refundable amount (${maxRefundable})`);
      }

      // Create refund record
      return await tx.refund.create({
        data: {
          paymentId: id,
          refundAmount,
          refundReason: validated.reason,
          refundStatus: 'REQUESTED',
          partialRefund: refundAmount < lockedPayment.amountTotal,
          requestedByAdminId: req.adminUser!.id,
          metadata: {
            reasonCode: validated.reasonCode,
            adminEmail: req.adminUser!.email,
          },
        },
      });
    });

    // Add to refund queue
    await paymentQueue.add('process-refund', {
      refundId: refund.id,
      paymentId: id,
      amount: refund.refundAmount,
      reason: validated.reason,
    });

    // Audit log
    await prisma.adminAuditLog.create({
      data: {
        adminUserId: req.adminUser!.id,
        action: 'REFUND_INITIATED',
        entityType: 'Refund',
        entityId: refund.id,
        beforeJson: { paymentStatus: payment.paymentStatus } as any,
        afterJson: { refundId: refund.id, amount: refund.refundAmount, reason: validated.reason } as any,
        ipAddress: req.ip || '127.0.0.1',
      },
    });

    logger.info(`Refund initiated: ${refund.id} for payment ${id} by ${req.adminUser!.email}`);

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
 * GET /api/admin/v2/refunds/:id
 * Get refund details
 */
export async function getRefundDetails(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const { id } = req.params;

    const refund = await prisma.refund.findUnique({
      where: { id },
      include: {
        payment: true,
      },
    });

    if (!refund) {
      return res.status(404).json({ error: 'Refund not found' });
    }

    return res.json(refund);
  } catch (error) {
    next(error);
  }
}
