import { Response, NextFunction } from 'express';
import prisma from '../repositories/db';
import { AuthenticatedAdminRequest } from '../middlewares/auth.middleware';
import logger from '../utils/logger';
import { z } from 'zod';

const reconciliationConfigSchema = z.object({
  targetMonth: z.string().regex(/^\d{4}-\d{2}$/), // YYYY-MM
  autoReconcile: z.boolean().optional(),
});

/**
 * GET /api/admin/v2/reconciliation/summary/:targetMonth
 * Get reconciliation summary for a month
 */
export async function getReconciliationSummary(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const { targetMonth } = req.params;

    // Parse target month
    const [year, month] = targetMonth.split('-').map(Number);
    const startDate = new Date(year, month - 1, 1);
    const endDate = new Date(year, month, 0, 23, 59, 59);

    // Get payments for the month
    const payments = await prisma.payment.findMany({
      where: {
        createdAt: {
          gte: startDate,
          lte: endDate,
        },
        paymentStatus: 'PAID',
      },
      include: {
        taxDocuments: true,
      },
    });

    // Get remittances for the month
    const remittances = await prisma.remittance.findMany({
      where: {
        remittedAt: {
          gte: startDate,
          lte: endDate,
        },
      },
    });

    // Calculate totals
    const totalPaymentAmount = payments.reduce((sum, p) => sum + p.amountTotal, 0);
    const totalTaxInvoiceAmount = payments
      .filter(p => p.taxDocuments && p.taxDocuments.length > 0)
      .reduce((sum, p) => sum + (p.amountSupply + p.amountVat), 0);
    
    const totalRemittanceUsd = remittances.reduce((sum, r) => sum + r.amountUsd, 0);
    const totalRemittanceKrw = remittances.reduce((sum, r) => sum + r.amountKrw, 0);

    // Calculate discrepancies
    const paymentVsTaxInvoice = totalPaymentAmount - totalTaxInvoiceAmount;
    const taxInvoiceVsRemittance = totalTaxInvoiceAmount - totalRemittanceKrw;

    // Get reconciliation log
    const reconciliationLog = await prisma.reconciliationLog.findFirst({
      where: { targetMonth },
    });

    const summary = {
      targetMonth,
      period: {
        start: startDate.toISOString(),
        end: endDate.toISOString(),
      },
      payments: {
        count: payments.length,
        totalAmount: totalPaymentAmount,
      },
      taxInvoices: {
        count: payments.filter(p => p.taxDocuments && p.taxDocuments.length > 0).length,
        totalAmount: totalTaxInvoiceAmount,
      },
      remittances: {
        count: remittances.length,
        totalUsd: totalRemittanceUsd,
        totalKrw: totalRemittanceKrw,
      },
      discrepancies: {
        paymentVsTaxInvoice,
        taxInvoiceVsRemittance,
        hasDiscrepancy: paymentVsTaxInvoice !== 0 || taxInvoiceVsRemittance !== 0,
      },
      reconciliation: reconciliationLog ? {
        status: reconciliationLog.status,
        reconciledAt: reconciliationLog.reconciledAt,
        reconciledBy: reconciliationLog.reconciledBy,
      } : null,
    };

    return res.json(summary);
  } catch (error) {
    next(error);
  }
}

/**
 * POST /api/admin/v2/reconciliation/auto
 * Run automatic reconciliation
 */
export async function runAutoReconciliation(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const validated = reconciliationConfigSchema.parse(req.body);
    const { targetMonth } = validated;

    // Parse target month
    const [year, month] = targetMonth.split('-').map(Number);
    const startDate = new Date(year, month - 1, 1);
    const endDate = new Date(year, month, 0, 23, 59, 59);

    // Get all payments for the month
    const payments = await prisma.payment.findMany({
      where: {
        createdAt: {
          gte: startDate,
          lte: endDate,
        },
        paymentStatus: 'PAID',
      },
      include: {
        taxDocuments: true,
      },
    });

    // Get all remittances for the month
    const remittances = await prisma.remittance.findMany({
      where: {
        remittedAt: {
          gte: startDate,
          lte: endDate,
        },
      },
    });

    // Match payments to remittances
    const matchedPayments: any[] = [];
    const unmatchedPayments: any[] = [];
    const matchedRemittances: any[] = [];
    const unmatchedRemittances: any[] = [...remittances];

    for (const payment of payments) {
      // Try to find matching remittance
      const matchingRemittance = unmatchedRemittances.find(r => 
        Math.abs(r.amountKrw - payment.amountTotal) < 1000 // Allow 1000 KRW difference
      );

      if (matchingRemittance) {
        matchedPayments.push({
          paymentId: payment.id,
          paymentAmount: payment.amountTotal,
          remittanceId: matchingRemittance.id,
          remittanceAmount: matchingRemittance.amountKrw,
          difference: payment.amountTotal - matchingRemittance.amountKrw,
        });
        matchedRemittances.push(matchingRemittance);
        unmatchedRemittances.splice(unmatchedRemittances.indexOf(matchingRemittance), 1);
      } else {
        unmatchedPayments.push({
          paymentId: payment.id,
          paymentAmount: payment.amountTotal,
          createdAt: payment.createdAt,
        });
      }
    }

    // Calculate totals for reconciliation log
    const totalPaymentAmount = payments.reduce((sum, p) => sum + p.amountTotal, 0);
    const totalTaxInvoiceAmount = payments
      .filter(p => p.taxDocuments && p.taxDocuments.length > 0)
      .reduce((sum, p) => sum + (p.amountSupply + p.amountVat), 0);
    const totalRemittanceKrw = remittances.reduce((sum, r) => sum + r.amountKrw, 0);
    const paymentVsTaxInvoice = totalPaymentAmount - totalTaxInvoiceAmount;

    // Create or update reconciliation log
    const reconciliationLog = await prisma.reconciliationLog.upsert({
      where: { targetMonth },
      create: {
        targetMonth,
        status: unmatchedPayments.length === 0 && unmatchedRemittances.length === 0 
          ? 'RECONCILED' 
          : 'PARTIAL',
        matchedPaymentsCount: matchedPayments.length,
        totalPgAmountKrw: totalPaymentAmount,
        totalTaxDocAmountKrw: totalTaxInvoiceAmount,
        totalRemittanceKrw: totalRemittanceKrw,
        varianceAmountKrw: paymentVsTaxInvoice,
        feeVarianceKrw: 0,
        reconciledBy: req.adminUser!.id,
        reconciledAt: new Date(),
        metadata: {
          matchedPayments,
          unmatchedPayments,
          matchedRemittances: matchedRemittances.map(r => r.id),
          unmatchedRemittances: unmatchedRemittances.map(r => ({
            id: r.id,
            amount: r.amountKrw,
            remittedAt: r.remittedAt,
          })),
        },
      },
      update: {
        status: unmatchedPayments.length === 0 && unmatchedRemittances.length === 0 
          ? 'RECONCILED' 
          : 'PARTIAL',
        matchedPaymentsCount: matchedPayments.length,
        totalPgAmountKrw: totalPaymentAmount,
        totalTaxDocAmountKrw: totalTaxInvoiceAmount,
        totalRemittanceKrw: totalRemittanceKrw,
        varianceAmountKrw: paymentVsTaxInvoice,
        feeVarianceKrw: 0,
        reconciledBy: req.adminUser!.id,
        reconciledAt: new Date(),
        metadata: {
          matchedPayments,
          unmatchedPayments,
          matchedRemittances: matchedRemittances.map(r => r.id),
          unmatchedRemittances: unmatchedRemittances.map(r => ({
            id: r.id,
            amount: r.amountKrw,
            remittedAt: r.remittedAt,
          })),
        },
      },
    });

    // Audit log
    await prisma.adminAuditLog.create({
      data: {
        adminUserId: req.adminUser!.id,
        action: 'AUTO_RECONCILIATION',
        entityType: 'ReconciliationLog',
        entityId: reconciliationLog.id,
        afterJson: {
          targetMonth,
          matched: matchedPayments.length,
          unmatchedPayments: unmatchedPayments.length,
          unmatchedRemittances: unmatchedRemittances.length,
        } as any,
        ipAddress: req.ip || '127.0.0.1',
      },
    });

    logger.info(`Auto reconciliation completed for ${targetMonth} by ${req.adminUser!.email}`);

    return res.json({
      success: true,
      reconciliation: {
        targetMonth,
        status: reconciliationLog.status,
        matched: matchedPayments.length,
        unmatchedPayments: unmatchedPayments.length,
        unmatchedRemittances: unmatchedRemittances.length,
        details: {
          matchedPayments,
          unmatchedPayments,
          unmatchedRemittances: unmatchedRemittances.map(r => ({
            id: r.id,
            amount: r.amountKrw,
            remittedAt: r.remittedAt,
          })),
        },
      },
    });
  } catch (error) {
    next(error);
  }
}

/**
 * GET /api/admin/v2/reconciliation/discrepancies/:targetMonth
 * Get discrepancies for a month
 */
export async function getDiscrepancies(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const { targetMonth } = req.params;

    const reconciliationLog = await prisma.reconciliationLog.findFirst({
      where: { targetMonth },
    });

    if (!reconciliationLog) {
      return res.status(404).json({ error: 'Reconciliation not found for this month' });
    }

    const metadata = reconciliationLog.metadata as any;

    return res.json({
      targetMonth,
      unmatchedPayments: metadata?.unmatchedPayments || [],
      unmatchedRemittances: metadata?.unmatchedRemittances || [],
      matchedPayments: metadata?.matchedPayments || [],
    });
  } catch (error) {
    next(error);
  }
}
