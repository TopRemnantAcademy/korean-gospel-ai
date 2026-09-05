import { Worker, Job } from 'bullmq';
import { connection, paymentQueue } from './queues';
import prisma from '../repositories/db';
import { decrypt, encrypt, sha256Hash } from '../utils/crypto';
import { isLocalIp } from '../utils/ip';
import { addPaymentTrace } from '../utils/audit';
import { TossPaymentsAdapter } from '../adapters/PgAdapter';
import TaxInvoiceAdapter from '../adapters/TaxAdapter';
import CashReceiptAdapter from '../adapters/CashReceiptAdapter';
import ChinaCreditAdapter from '../adapters/ChinaAdapter';
import { MS_PER_DAY } from '../constants/time';
import { 
  PaymentStatus, 
  DispatchStatus, 
  DocumentIssueStatus, 
  CashReceiptStatus, 
  RefundStatus,
  InvoiceType,
  ReceiptType,
  OrderStatus,
  CashReceiptType,
  CashReceiptIdentityType
} from '@gospel-pay/shared';
import logger from '../utils/logger';

const pgAdapter = new TossPaymentsAdapter();
const taxAdapter = new TaxInvoiceAdapter();
const cashReceiptAdapter = new CashReceiptAdapter();
const chinaAdapter = new ChinaCreditAdapter();

export const paymentWorker = new Worker(
  'payment-tasks',
  async (job: Job) => {
    logger.info(`Starting job: ${job.name} (ID: ${job.id})`);
    
    switch (job.name) {
      case 'ISSUE_TAX_DOCUMENT':
        await handleIssueTaxDocument(job);
        break;
      case 'CANCEL_TAX_DOCUMENT':
        await handleCancelTaxDocument(job);
        break;
      case 'ISSUE_CASH_RECEIPT':
        await handleIssueCashReceipt(job);
        break;
      case 'CANCEL_CASH_RECEIPT':
        await handleCancelCashReceipt(job);
        break;
      case 'SEND_CREDIT':
        await handleSendCredit(job);
        break;
      case 'PROCESS_REFUND':
        await handleProcessRefund(job);
        break;
      case 'REVERSE_CREDIT':
        await handleReverseCredit(job);
        break;
      case 'DATA_RETENTION_CLEANUP':
        await handleDataRetentionCleanup(job);
        break;
      default:
        logger.warn(`Unknown job name: ${job.name}`);
    }
  },
  { connection }
);

// Worker Event Listeners
paymentWorker.on('completed', (job) => {
  logger.info(`Job completed: ${job.name} (ID: ${job.id})`);
});

paymentWorker.on('failed', (job, err) => {
  logger.error(`Job failed: ${job?.name} (ID: ${job?.id}) - Error: ${err.message}`);
});

/**
 * Job: ISSUE_TAX_DOCUMENT
 */
async function handleIssueTaxDocument(job: Job) {
  const { paymentId } = job.data;
  
  const payment = await prisma.payment.findUnique({
    where: { id: paymentId },
    include: { taxDocuments: true },
  });

  if (!payment) {
    throw new Error(`Payment not found for Tax Document: ${paymentId}`);
  }

  // Create or retrieve TaxDocument record
  let taxDoc = payment.taxDocuments[0];
  if (!taxDoc) {
    taxDoc = await prisma.taxDocument.create({
      data: {
        paymentId,
        invoiceType: payment.invoiceType || InvoiceType.TAX_INVOICE,
        provider: 'TAX_INVOICE_PROVIDER',
        issueStatus: DocumentIssueStatus.READY,
      },
    });
  }

  // Set processing state
  await prisma.taxDocument.update({
    where: { id: taxDoc.id },
    data: { 
      issueStatus: DocumentIssueStatus.PROCESSING,
      issueAttempts: { increment: 1 },
    },
  });

  await prisma.payment.update({
    where: { id: paymentId },
    data: { invoiceRequestStatus: DocumentIssueStatus.PROCESSING },
  });

  await addPaymentTrace(paymentId, 'TAX_DOCUMENT', 'INITIATED', 'Initiating tax invoice/invoice issuance request to domestic provider.');

  try {
    if (!payment.companyRegNumberEncrypted || !payment.taxEmailEncrypted) {
      throw new Error('Missing encrypted B2B fields (companyRegNumber or taxEmail) required for tax document issuance');
    }
    const decRegNo = decrypt(payment.companyRegNumberEncrypted) as string;
    const decTaxEmail = decrypt(payment.taxEmailEncrypted) as string;
    
    let result;
    if (payment.invoiceType === InvoiceType.TAX_INVOICE) {
      result = await taxAdapter.issueTaxInvoice({
        paymentId: payment.id,
        companyRegNumber: decRegNo,
        companyName: payment.companyName || '',
        ceoName: payment.ceoName || '',
        taxEmail: decTaxEmail,
        amountSupply: payment.amountSupply,
        amountVat: payment.amountVat,
      });
    } else {
      result = await taxAdapter.issueInvoice({
        paymentId: payment.id,
        companyRegNumber: decRegNo,
        companyName: payment.companyName || '',
        ceoName: payment.ceoName || '',
        taxEmail: decTaxEmail,
        amountTotal: payment.amountTotal,
      });
    }

    if (result.success) {
      await prisma.taxDocument.update({
        where: { id: taxDoc.id },
        data: {
          issueStatus: DocumentIssueStatus.SENT,
          providerDocumentId: result.providerDocumentId,
          issuedAt: new Date(),
        },
      });

      await prisma.payment.update({
        where: { id: paymentId },
        data: {
          invoiceRequestStatus: DocumentIssueStatus.SENT,
          invoiceDocumentId: result.providerDocumentId,
        },
      });

      await addPaymentTrace(paymentId, 'TAX_DOCUMENT', 'SUCCESS', `Successfully issued tax invoice. Document ID: ${result.providerDocumentId}`);
    } else {
      throw new Error(result.errorMessage || 'Unknown Tax Invoice generation error');
    }
  } catch (error: any) {
    await prisma.taxDocument.update({
      where: { id: taxDoc.id },
      data: {
        issueStatus: DocumentIssueStatus.FAILED,
        lastErrorMessage: error.message,
      },
    });

    await prisma.payment.update({
      where: { id: paymentId },
      data: { invoiceRequestStatus: DocumentIssueStatus.FAILED },
    });

    await addPaymentTrace(paymentId, 'TAX_DOCUMENT', 'FAILED', `Failed to issue tax invoice: ${error.message}`);

    throw error; // Let BullMQ retry
  }
}

/**
 * Job: ISSUE_CASH_RECEIPT
 */
async function handleIssueCashReceipt(job: Job) {
  const { paymentId } = job.data;

  const payment = await prisma.payment.findUnique({
    where: { id: paymentId },
    include: { cashReceipts: true },
  });

  if (!payment) {
    throw new Error(`Payment not found for Cash Receipt: ${paymentId}`);
  }

  const receipt = payment.cashReceipts[0];
  if (!receipt) {
    throw new Error(`Cash receipt metadata not found for Payment: ${paymentId}`);
  }

  await prisma.cashReceipt.update({
    where: { id: receipt.id },
    data: {
      receiptStatus: CashReceiptStatus.PROCESSING,
      attempts: { increment: 1 },
    },
  });

  await addPaymentTrace(paymentId, 'CASH_RECEIPT', 'INITIATED', 'Initiating cash receipt issuance request to domestic provider.');

  try {
    if (!receipt.identityValueEncrypted) {
      throw new Error('Missing encrypted identity value for cash receipt issuance');
    }
    const decIdentity = decrypt(receipt.identityValueEncrypted) as string;

    // Validate cash receipt type and identity type
    if (!Object.values(CashReceiptType).includes(receipt.receiptType)) {
      throw new Error(`Invalid cash receipt type: ${receipt.receiptType}`);
    }
    if (!Object.values(CashReceiptIdentityType).includes(receipt.identityType)) {
      throw new Error(`Invalid cash receipt identity type: ${receipt.identityType}`);
    }

    const result = await cashReceiptAdapter.issueCashReceipt({
      paymentId: payment.id,
      amount: payment.amountTotal,
      receiptType: receipt.receiptType,
      identityType: receipt.identityType,
      identityValue: decIdentity,
    });

    if (result.success) {
      await prisma.cashReceipt.update({
        where: { id: receipt.id },
        data: {
          receiptStatus: CashReceiptStatus.SENT,
          providerReceiptId: result.providerReceiptId,
          issuedAt: new Date(),
        },
      });

      await addPaymentTrace(paymentId, 'CASH_RECEIPT', 'SUCCESS', `Successfully issued cash receipt. Receipt ID: ${result.providerReceiptId}`);
    } else {
      throw new Error(result.errorMessage || 'Cash Receipt issue failed');
    }
  } catch (error: any) {
    await prisma.cashReceipt.update({
      where: { id: receipt.id },
      data: {
        receiptStatus: CashReceiptStatus.FAILED,
        lastErrorMessage: error.message,
      },
    });

    await addPaymentTrace(paymentId, 'CASH_RECEIPT', 'FAILED', `Failed to issue cash receipt: ${error.message}`);

    throw error;
  }
}

/**
 * Job: SEND_CREDIT
 */
async function handleSendCredit(job: Job) {
  const { paymentId } = job.data;

  const payment = await prisma.payment.findUnique({
    where: { id: paymentId },
    include: { creditDispatches: true },
  });

  if (!payment) {
    throw new Error(`Payment not found for Credit allocation: ${paymentId}`);
  }

  let dispatch = payment.creditDispatches[0];
  if (!dispatch) {
    dispatch = await prisma.creditDispatch.create({
      data: {
        paymentId,
        uid: payment.userUid,
        creditedAmount: payment.creditAmount,
        dispatchStatus: DispatchStatus.READY,
      },
    });
  }

  await prisma.creditDispatch.update({
    where: { id: dispatch.id },
    data: {
      dispatchStatus: DispatchStatus.PROCESSING,
      attempts: { increment: 1 },
    },
  });

  await prisma.payment.update({
    where: { id: paymentId },
    data: { creditStatus: DispatchStatus.PROCESSING },
  });

  await addPaymentTrace(paymentId, 'CREDIT_DISPATCH', 'INITIATED', 'Initiating credit synchronization request to remote platform server.');

  try {
    const result = await chinaAdapter.sendCredit({
      paymentId: payment.id,
      uid: payment.userUid,
      creditedAmount: payment.creditAmount,
      paymentRef: payment.paymentUuid,
    });

    if (result.success) {
      await prisma.creditDispatch.update({
        where: { id: dispatch.id },
        data: {
          dispatchStatus: DispatchStatus.SENT,
          dispatchedAt: new Date(),
          requestPayload: result.requestPayload,
          responsePayload: result.responsePayload,
        },
      });

      await prisma.payment.update({
        where: { id: paymentId },
        data: {
          creditStatus: DispatchStatus.SENT,
        },
      });

      await addPaymentTrace(paymentId, 'CREDIT_DISPATCH', 'SUCCESS', `Successfully sent credit allocation request for ${payment.creditAmount} credits to remote platform.`);
      await addPaymentTrace(paymentId, 'CHINA_WEBHOOK', 'INITIATED', 'Awaiting confirmation webhook callback from remote platform...');
    } else {
      throw new Error(result.errorMessage || 'Remote platform credit topup call failed');
    }
  } catch (error: any) {
    await prisma.creditDispatch.update({
      where: { id: dispatch.id },
      data: {
        dispatchStatus: DispatchStatus.FAILED,
        lastErrorMessage: error.message,
      },
    });

    await prisma.payment.update({
      where: { id: paymentId },
      data: { creditStatus: DispatchStatus.FAILED },
    });

    await addPaymentTrace(paymentId, 'CREDIT_DISPATCH', 'FAILED', `Failed to sync credits to remote server: ${error.message}`);

    throw error;
  }
}

/**
 * Job: PROCESS_REFUND
 */
async function handleProcessRefund(job: Job) {
  const { refundId } = job.data;

  const refund = await prisma.refund.findUnique({
    where: { id: refundId },
    include: { payment: true },
  });

  if (!refund) {
    throw new Error(`Refund record not found: ${refundId}`);
  }

  await prisma.refund.update({
    where: { id: refundId },
    data: { refundStatus: RefundStatus.PROCESSING },
  });

  try {
    const payment = refund.payment;
    
    let refundAccount;
    if (refund.requiresRefundAccount && refund.refundAccountNumberEncrypted) {
      refundAccount = {
        bankCode: refund.refundBankCode!,
        accountNumber: decrypt(refund.refundAccountNumberEncrypted) as string,
        accountHolder: refund.refundAccountHolder!,
      };
    }

    const cancelResult = await pgAdapter.refundPayment(
      payment.pgTransactionId || payment.paymentUuid,
      refund.refundAmount,
      refund.refundReason,
      refundAccount,
      payment.id
    );

    if (!cancelResult.success) {
      throw new Error(cancelResult.errorMessage || 'PG refund call failed');
    }

    // Complete refund database updates
    await prisma.$transaction(async (tx) => {
      await tx.refund.update({
        where: { id: refundId },
        data: {
          refundStatus: RefundStatus.DONE,
          pgRefundId: cancelResult.pgRefundId,
        },
      });

      // Calculate total refunded so far
      const allRefunds = await tx.refund.findMany({
        where: { paymentId: payment.id, refundStatus: RefundStatus.DONE },
      });
      const totalRefunded = allRefunds.reduce((sum, r) => sum + r.refundAmount, 0);

      let newStatus: PaymentStatus = PaymentStatus.PARTIALLY_REFUNDED;
      if (totalRefunded >= payment.amountTotal) {
        newStatus = PaymentStatus.REFUNDED;
      }

      await tx.payment.update({
        where: { id: payment.id },
        data: {
          paymentStatus: newStatus,
          refundedAt: new Date(),
        },
      });

      // Update OrderStatus as well
      await tx.paymentOrder.update({
        where: { id: payment.paymentOrderId },
        data: { orderStatus: newStatus as unknown as OrderStatus },
      });
    });

    // Enqueue follow-up credit reversal on Chinese server
    await prisma.creditDispatch.updateMany({
      where: { paymentId: payment.id },
      data: { dispatchStatus: DispatchStatus.REVERSED },
    });

    // Allocate queue task for reversing credit
    await paymentQueue.add('REVERSE_CREDIT', {
      paymentId: payment.id,
      refundId: refund.id,
    });

    // Handle tax/cash receipt cancellations
    if ((payment.receiptType === ReceiptType.TAX_INVOICE || payment.receiptType === ReceiptType.INVOICE) && payment.invoiceDocumentId) {
      await paymentQueue.add('CANCEL_TAX_DOCUMENT', { paymentId: payment.id, refundId: refund.id });
    } else if (payment.receiptType === ReceiptType.CASH_RECEIPT) {
      await paymentQueue.add('CANCEL_CASH_RECEIPT', { paymentId: payment.id, refundId: refund.id });
    }

  } catch (error: any) {
    await prisma.refund.update({
      where: { id: refundId },
      data: { refundStatus: RefundStatus.FAILED },
    });
    throw error;
  }
}

/**
 * Job: REVERSE_CREDIT
 */
async function handleReverseCredit(job: Job) {
  const { paymentId, refundId } = job.data;

  const payment = await prisma.payment.findUnique({
    where: { id: paymentId },
  });

  const refund = await prisma.refund.findUnique({
    where: { id: refundId },
  });

  if (!payment || !refund) {
    throw new Error('Payment or Refund not found for reversal');
  }

  // Validate payment amount to prevent division by zero
  if (payment.amountTotal <= 0) {
    throw new Error('Invalid payment amount: must be positive');
  }

  try {
    const result = await chinaAdapter.reverseCredit({
      paymentId: payment.id,
      refundId: refund.id,
      uid: payment.userUid,
      creditedAmount: refund.refundAmount === payment.amountTotal ? payment.creditAmount : Math.round((refund.refundAmount / payment.amountTotal) * payment.creditAmount),
      paymentRef: payment.paymentUuid,
    });

    if (result.success) {
      await prisma.refund.update({
        where: { id: refundId },
        data: { creditReversalStatus: DispatchStatus.REVERSED },
      });
    } else {
      throw new Error(result.errorMessage || 'China credit reversal failed');
    }
  } catch (error: any) {
    await prisma.refund.update({
      where: { id: refundId },
      data: { creditReversalStatus: DispatchStatus.FAILED },
    });
    throw error;
  }
}

/**
 * Job: DATA_RETENTION_CLEANUP
 */
export async function handleDataRetentionCleanup(job: Job) {
  logger.info('Starting Data Retention Cleanup Worker task...');
  
  // 1. Fetch policies
  const policies = await prisma.dataRetentionPolicy.findMany({
    where: { isActive: true },
  });

  const now = new Date();

  for (const policy of policies) {
    const thresholdDate = new Date(now.getTime() - policy.retentionDays * MS_PER_DAY);
    logger.info(`Running policy: ${policy.dataCategory} (Older than ${policy.retentionDays} days, before ${thresholdDate.toISOString()})`);

    if (policy.dataCategory === 'PII_DELETED_USERS') {
      // Clean up users flagged as deleted
      const deletedUsers = await prisma.user.findMany({
        where: {
          isDeleted: true,
          deletedAt: { lt: thresholdDate },
          OR: [
            { emailEncrypted: { not: null } },
            { phoneEncrypted: { not: null } },
          ],
        },
      });

      for (const u of deletedUsers) {
        if (isLocalIp(u.registeredIp)) {
          logger.info(`Bypassing PII cleanup for local user: ${u.id} (IP: ${u.registeredIp}) due to local data retention policy.`);
          continue;
        }

        await prisma.user.update({
          where: { id: u.id },
          data: {
            emailEncrypted: null,
            emailHash: null,
            phoneEncrypted: null,
            phoneHash: null,
            phoneLast4: null,
          },
        });
        
        await prisma.adminAuditLog.create({
          data: {
            adminUserId: null,
            action: 'DISPOSAL_PII',
            entityType: 'User',
            entityId: u.id,
            beforeJson: { uid: u.uid },
            afterJson: { uid: u.uid, pii: 'Disposed/Masked' },
            ipAddress: '127.0.0.1',
          },
        });
      }
      logger.info(`Cleaned up ${deletedUsers.length} deleted users.`);
    }

    if (policy.dataCategory === 'PAYMENT_RAW_PAYLOADS') {
      // Anonymize raw PG callback payloads older than policy days to remove any internal addresses/numbers
      const oldPayments = await prisma.payment.findMany({
        where: {
          createdAt: { lt: thresholdDate },
          rawPgPayload: { not: null as any },
        },
        include: {
          user: true,
        },
      });

      for (const p of oldPayments) {
        if (p.user && isLocalIp(p.user.registeredIp)) {
          logger.info(`Bypassing payment payload masking for local user payment: ${p.id} (User IP: ${p.user.registeredIp}) due to local data retention policy.`);
          continue;
        }

        await prisma.payment.update({
          where: { id: p.id },
          data: {
            rawPgPayload: null as any,
            companyRegNumberEncrypted: null,
            companyRegNumberHash: null,
            taxEmailEncrypted: null,
            taxEmailHash: null,
          },
        });

        await prisma.adminAuditLog.create({
          data: {
            adminUserId: null,
            action: 'DISPOSAL_PAYMENT_PII',
            entityType: 'Payment',
            entityId: p.id,
            beforeJson: { paymentUuid: p.paymentUuid },
            afterJson: { paymentUuid: p.paymentUuid, rawPgPayload: 'Cleaned' },
            ipAddress: '127.0.0.1',
          },
        });
      }
      logger.info(`Cleaned up ${oldPayments.length} old payment payloads.`);
    }
  }

  // 3. Clean up expired payment orders that were never paid (INITIATED state passed expiresAt)
  const expiredCount = await prisma.paymentOrder.updateMany({
    where: {
      orderStatus: OrderStatus.INITIATED,
      expiresAt: { lt: now },
    },
    data: {
      orderStatus: OrderStatus.EXPIRED,
    },
  });
  if (expiredCount.count > 0) {
    logger.info(`Cleaned up ${expiredCount.count} expired initiated payment orders.`);
  }
}

/**
 * Job: CANCEL_TAX_DOCUMENT
 */
async function handleCancelTaxDocument(job: Job) {
  const { paymentId, refundId } = job.data;
  const payment = await prisma.payment.findUnique({
    where: { id: paymentId },
    include: { taxDocuments: true },
  });

  if (!payment || !payment.invoiceDocumentId) {
    logger.warn(`Payment or Tax Invoice ID not found to cancel: ${paymentId}`);
    return;
  }

  // Read actual refund amount for partial adjust billing
  let cancelAmount = payment.amountTotal;
  if (refundId) {
    const refund = await prisma.refund.findUnique({
      where: { id: refundId },
    });
    if (refund) {
      cancelAmount = refund.refundAmount;
    }
  }

  try {
    const result = await taxAdapter.cancelOrAdjustDocument(
      payment.id,
      payment.invoiceDocumentId,
      -cancelAmount,
      '결제 환불로 인한 수정분 발행 취소'
    );

    if (result.success) {
      await prisma.taxDocument.updateMany({
        where: { paymentId },
        data: { issueStatus: DocumentIssueStatus.CANCELLED },
      });
      await prisma.payment.update({
        where: { id: paymentId },
        data: { invoiceRequestStatus: DocumentIssueStatus.CANCELLED },
      });
    } else {
      throw new Error(result.errorMessage || 'Tax invoice cancellation failed');
    }
  } catch (error: any) {
    logger.error(`Failed to cancel tax document for payment ${paymentId}: ${error.message}`);
    throw error;
  }
}

/**
 * Job: CANCEL_CASH_RECEIPT
 */
async function handleCancelCashReceipt(job: Job) {
  const { paymentId, refundId } = job.data;
  const payment = await prisma.payment.findUnique({
    where: { id: paymentId },
    include: { cashReceipts: true },
  });

  const receipt = payment?.cashReceipts[0];
  if (!payment || !receipt || !receipt.providerReceiptId) {
    logger.warn(`Payment or Cash receipt key not found to cancel: ${paymentId}`);
    return;
  }

  // Read actual refund amount for partial cash receipt cancellation
  let cancelAmount = payment.amountTotal;
  if (refundId) {
    const refund = await prisma.refund.findUnique({
      where: { id: refundId },
    });
    if (refund) {
      cancelAmount = refund.refundAmount;
    }
  }

  try {
    const result = await cashReceiptAdapter.cancelCashReceipt({
      paymentId: payment.id,
      providerReceiptId: receipt.providerReceiptId,
      amount: cancelAmount,
    });

    if (result.success) {
      await prisma.cashReceipt.update({
        where: { id: receipt.id },
        data: { receiptStatus: CashReceiptStatus.CANCELLED },
      });
    } else {
      throw new Error(result.errorMessage || 'Cash receipt cancellation failed');
    }
  } catch (error: any) {
    logger.error(`Failed to cancel cash receipt for payment ${paymentId}: ${error.message}`);
    throw error;
  }
}
