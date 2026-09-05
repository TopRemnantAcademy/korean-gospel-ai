import { Request, Response, NextFunction } from 'express';
import prisma from '../repositories/db';
import logger from '../utils/logger';
import { PaymentStatus, DocumentIssueStatus, ReconciliationStatus } from '@gospel-pay/shared';

/**
 * POST /api/admin/reconciliation/import
 * Imports bank remittance records from a CSV string sent in the body.
 */
export async function importRemittances(req: Request, res: Response, next: NextFunction) {
  try {
    const { csvData } = req.body;
    if (!csvData) {
      return res.status(400).json({ error: 'CSV data is required.' });
    }

    // Validate CSV size (max 5MB)
    const csvSize = Buffer.byteLength(csvData, 'utf8');
    if (csvSize > 5 * 1024 * 1024) {
      return res.status(400).json({ error: 'CSV file too large. Maximum size is 5MB.' });
    }

    const lines = csvData.split('\n');
    
    // Validate row count (max 10,000 rows)
    if (lines.length > 10000) {
      return res.status(400).json({ error: 'Too many rows. Maximum is 10,000 rows.' });
    }
    
    let importedCount = 0;
    let skippedCount = 0;

    // Expected headers: date,remittanceKey,bankName,amountUsd,exchangeRate,feeUsd,feeKrw,justification
    for (let i = 1; i < lines.length; i++) {
      const line = lines[i].trim();
      if (!line) continue;

      const columns = line.split(',');
      if (columns.length < 5) {
        skippedCount++;
        continue;
      }

      const [dateStr, remittanceKey, bankName, amountUsdStr, exchangeRateStr, feeUsdStr, feeKrwStr, justification] = columns;

      // Sanitize CSV fields to prevent CSV injection
      const sanitizedRemittanceKey = remittanceKey.trim().replace(/[=\+\-@]/g, '');
      const sanitizedBankName = bankName.trim().replace(/[=\+\-@]/g, '');
      const sanitizedJustification = justification ? justification.trim().replace(/[=\+\-@]/g, '') : null;

      if (!remittanceKey || !amountUsdStr || !exchangeRateStr) {
        skippedCount++;
        continue;
      }

      const remittedAt = new Date(dateStr.trim());
      if (isNaN(remittedAt.getTime())) {
        logger.warn(`Invalid date format in CSV line ${i}: ${dateStr}`);
        skippedCount++;
        continue;
      }

      // Schema stores Int: amountUsd in cents, exchangeRate in basis points, feeUsd in cents
      const amountUsdFloat = parseFloat(amountUsdStr.trim());
      const exchangeRateFloat = parseFloat(exchangeRateStr.trim());
      const feeUsdFloat = feeUsdStr ? parseFloat(feeUsdStr.trim()) : 0;

      if (isNaN(amountUsdFloat) || isNaN(exchangeRateFloat)) {
        skippedCount++;
        continue;
      }

      const amountUsd = Math.round(amountUsdFloat * 100); // Convert to cents
      const exchangeRate = Math.round(exchangeRateFloat * 100); // Convert to basis points
      const feeUsd = Math.round(feeUsdFloat * 100); // Convert to cents
      const feeKrw = feeKrwStr ? (parseInt(feeKrwStr.trim(), 10) || 0) : 0;
      const amountKrw = Math.round(amountUsdFloat * exchangeRateFloat);
      
      // Validate calculated values don't exceed safe integer limits
      if (amountUsd > Number.MAX_SAFE_INTEGER || exchangeRate > Number.MAX_SAFE_INTEGER || amountKrw > Number.MAX_SAFE_INTEGER) {
        logger.warn(`Integer overflow detected in CSV line ${i}`);
        skippedCount++;
        continue;
      }

      // Check duplicate
      const existing = await prisma.remittance.findUnique({
        where: { remittanceKey: sanitizedRemittanceKey },
      });

      if (existing) {
        skippedCount++;
        continue;
      }

      await prisma.remittance.create({
        data: {
          remittedAt,
          remittanceKey: sanitizedRemittanceKey,
          bankName: sanitizedBankName,
          amountUsd,
          exchangeRate,
          amountKrw,
          feeUsd,
          feeKrw,
          justification: sanitizedJustification,
        },
      });
      importedCount++;
    }

    return res.status(201).json({
      success: true,
      message: `성공적으로 ${importedCount}건의 송금 데이터를 가져왔습니다. (${skippedCount}건 스킵)`,
      importedCount,
      skippedCount,
    });
  } catch (error) {
    next(error);
  }
}

/**
 * POST /api/admin/reconciliation/run
 * Runs monthly 3-way matching and logs exchange variances and fees.
 */
export async function runReconciliation(req: Request, res: Response, next: NextFunction) {
  try {
    const { month } = req.body; // format: "YYYY-MM"
    if (!month || !/^\d{4}-\d{2}$/.test(month)) {
      return res.status(400).json({ error: '올바른 연월 형식(YYYY-MM)이 필요합니다.' });
    }

    const startDate = new Date(`${month}-01T00:00:00.000Z`);
    const endDate = new Date(new Date(`${month}-01T00:00:00.000Z`).setMonth(startDate.getMonth() + 1));

    // 1. Fetch remittances for the target month
    const remittances = await prisma.remittance.findMany({
      where: {
        remittedAt: {
          gte: startDate,
          lt: endDate,
        },
      },
    });

    if (remittances.length === 0) {
      return res.status(404).json({ error: '해당 연월에 대한 송금 데이터가 존재하지 않습니다.' });
    }

    // 2. Fetch paid payments for the target month
    const payments = await prisma.payment.findMany({
      where: {
        paymentStatus: PaymentStatus.PAID,
        paidAt: {
          gte: startDate,
          lt: endDate,
        },
      },
      include: {
        taxDocuments: {
          where: {
            issueStatus: DocumentIssueStatus.SENT,
          },
        },
      },
    });

    // Link payments to the first remittance of the month for database tracking
    // Use transaction to ensure atomicity
    const mainRemittance = remittances[0];
    await prisma.$transaction(async (tx) => {
      for (const payment of payments) {
        await tx.payment.update({
          where: { id: payment.id },
          data: { remittanceId: mainRemittance.id },
        });
      }
    });

    // Calculate aggregated metrics
    const matchedPaymentsCount = payments.length;
    const totalPgAmountKrw = payments.reduce((sum, p) => sum + p.amountTotal, 0);
    
    // Total amount in Popbill tax invoices
    const totalTaxDocAmountKrw = payments.reduce((sum, p) => {
      const doc = p.taxDocuments[0];
      return sum + (doc ? p.amountSupply + p.amountVat : 0);
    }, 0);

    const totalRemittanceKrw = remittances.reduce((sum, r) => sum + r.amountKrw, 0);
    const totalFeesKrw = remittances.reduce((sum, r) => sum + r.feeKrw, 0);

    // Variance calculation
    // Converted KRW value compared to domestic PG collections
    const varianceAmountKrw = totalPgAmountKrw - totalRemittanceKrw;
    
    let fxLossKrw = 0;
    let fxGainKrw = 0;

    if (varianceAmountKrw < 0) {
      // Deficit: Converted remittance is larger than collections, meaning exchange loss or fee variance occurred
      const absVariance = Math.abs(varianceAmountKrw);
      fxLossKrw = Math.max(0, absVariance - totalFeesKrw);
    } else {
      // Surplus: Collections are larger than converted remittance (exchange gain)
      fxGainKrw = varianceAmountKrw;
    }

    // Determine status
    const status = Math.abs(totalPgAmountKrw - totalTaxDocAmountKrw) > 0 ? ReconciliationStatus.DISCREPANCY_FLAGGED : ReconciliationStatus.AUTO_MATCHED;

    // Save or update ReconciliationLog
    const existingLog = await prisma.reconciliationLog.findUnique({
      where: { remittanceId: mainRemittance.id },
    });

    let reconLog;
    if (existingLog) {
      reconLog = await prisma.reconciliationLog.update({
        where: { id: existingLog.id },
        data: {
          targetMonth: month,
          status,
          matchedPaymentsCount,
          totalPgAmountKrw,
          totalTaxDocAmountKrw,
          totalRemittanceKrw,
          varianceAmountKrw,
          feeVarianceKrw: totalFeesKrw,
          fxLossKrw,
          fxGainKrw,
          verifiedAt: new Date(),
        },
      });
    } else {
      reconLog = await prisma.reconciliationLog.create({
        data: {
          targetMonth: month,
          status,
          remittanceId: mainRemittance.id,
          matchedPaymentsCount,
          totalPgAmountKrw,
          totalTaxDocAmountKrw,
          totalRemittanceKrw,
          varianceAmountKrw,
          feeVarianceKrw: totalFeesKrw,
          fxLossKrw,
          fxGainKrw,
          verifiedAt: new Date(),
        },
      });
    }

    logger.info(`Run reconciliation for month ${month}: totalPg=${totalPgAmountKrw}, totalRemittance=${totalRemittanceKrw}, status=${status}`);

    return res.json({
      success: true,
      reconLog,
    });
  } catch (error) {
    next(error);
  }
}

/**
 * GET /api/admin/reconciliation/logs
 * Lists all reconciliation logs.
 */
export async function getReconciliationLogs(req: Request, res: Response, next: NextFunction) {
  try {
    const logs = await prisma.reconciliationLog.findMany({
      include: {
        remittance: true,
      },
      orderBy: {
        targetMonth: 'desc',
      },
    });

    return res.json(logs);
  } catch (error) {
    next(error);
  }
}

/**
 * GET /api/admin/reconciliation/report
 * Streams reconciliation CSV report.
 */
export async function downloadReconciliationReport(req: Request, res: Response, next: NextFunction) {
  try {
    const { month } = req.query;
    if (!month || typeof month !== 'string') {
      return res.status(400).json({ error: 'Month parameter (YYYY-MM) is required.' });
    }

    const log = await prisma.reconciliationLog.findFirst({
      where: { targetMonth: month },
      include: {
        remittance: true,
      },
    });

    if (!log) {
      return res.status(404).json({ error: '해당 연월에 대한 정산 대조 내역이 존재하지 않습니다.' });
    }

    // Fetch payments associated with this month
    const startDate = new Date(`${month}-01T00:00:00.000Z`);
    const endDate = new Date(new Date(`${month}-01T00:00:00.000Z`).setMonth(startDate.getMonth() + 1));
    const payments = await prisma.payment.findMany({
      where: {
        paymentStatus: PaymentStatus.PAID,
        paidAt: {
          gte: startDate,
          lt: endDate,
        },
      },
    });

    // Write CSV Content
    let csv = '\uFEFF'; // UTF-8 BOM
    csv += '3-Way Reconciliation Report,Target Month: ' + month + '\n';
    csv += `Reconciliation Status,${log.status}\n`;
    csv += `Total PG Payments Count,${log.matchedPaymentsCount}\n`;
    csv += `Total PG Collections (KRW),${log.totalPgAmountKrw}\n`;
    csv += `Total Popbill Tax Invoices (KRW),${log.totalTaxDocAmountKrw}\n`;
    csv += `Total Remittance Value (KRW),${log.totalRemittanceKrw}\n`;
    csv += `Outbound Remittance USD,${log.remittance ? (log.remittance.amountUsd / 100).toFixed(2) : '0.00'}\n`;
    csv += `Applied Exchange Rate,${log.remittance ? (log.remittance.exchangeRate / 100).toFixed(2) : '0.00'}\n`;
    csv += `Outbound Bank Fees (KRW),${log.feeVarianceKrw}\n`;
    csv += `Exchange Loss (환차손 - KRW),${log.fxLossKrw}\n`;
    csv += `Exchange Gain (환차익 - KRW),${log.fxGainKrw}\n\n`;

    csv += 'Transaction Details\n';
    csv += 'Payment UUID,Date,Customer UID,Payment Method,Amount KRW\n';
    for (const p of payments) {
      csv += `${p.paymentUuid},${p.paidAt ? p.paidAt.toISOString() : ''},${p.userUid},${p.paymentMethod},${p.amountTotal}\n`;
    }

    res.setHeader('Content-Type', 'text/csv; charset=utf-8');
    res.setHeader('Content-Disposition', `attachment; filename="Reconciliation_Report_${month}.csv"`);
    return res.send(csv);
  } catch (error) {
    next(error);
  }
}
