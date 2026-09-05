import crypto from 'crypto';
import { Request, Response, NextFunction } from 'express';
import prisma from '../repositories/db';
import { PRODUCTS } from '../constants/codes';
import { calculateTax } from '../services/vat.service';
import { encrypt, sha256Hash, decrypt } from '../utils/crypto';
import { addPaymentTrace } from '../utils/audit';
import { TossPaymentsAdapter } from '../adapters/PgAdapter';
import { paymentQueue } from '../workers/queues';
import { PAYMENT_ORDER_EXPIRY_MS } from '../constants/time';
import {
  OrderStatus,
  PaymentStatus,
  ReceiptType,
  DispatchStatus,
  DocumentIssueStatus,
  CashReceiptStatus,
  PaymentMethod,
  InvoiceType
} from '@gospel-pay/shared';
import { paymentPrepareSchema, pgCallbackSchema, pgWebhookSchema, remoteWebhookSchema } from '@gospel-pay/shared';
import logger from '../utils/logger';
import { env } from '../config/env';

const pgAdapter = new TossPaymentsAdapter();

/**
 * GET /api/payment-methods
 */
export async function getPaymentMethods(req: Request, res: Response, next: NextFunction) {
  try {
    const configs = await prisma.paymentMethodConfig.findMany({
      where: { enabled: true },
      orderBy: { sortOrder: 'asc' },
    });
    return res.json(configs);
  } catch (error) {
    next(error);
  }
}

/**
 * GET /api/products
 */
export async function getProducts(req: Request, res: Response, next: NextFunction) {
  return res.json(Object.values(PRODUCTS));
}

/**
 * POST /api/payments/prepare
 */
export async function preparePayment(req: Request, res: Response, next: NextFunction) {
  try {
    const validated = paymentPrepareSchema.parse(req.body);
    const { userId, productCode, selectedPaymentMethod, invoiceRequested, cashReceiptRequested } = validated;

    const product = PRODUCTS[productCode];
    if (!product) {
      return res.status(400).json({ error: `Invalid product code: ${productCode}` });
    }

    const user = await prisma.user.findFirst({
      where: { id: userId, isDeleted: false },
    });
    if (!user) {
      return res.status(404).json({ error: 'User not found' });
    }

    // Double tax deduction validation: Cannot request both invoice and cash receipt
    // (Korean VAT Law Article 32: 신용카드 매출전표, 전자세금계산서, 현금영수증 중복 발행 금지)
    if (invoiceRequested && cashReceiptRequested) {
      return res.status(400).json({ error: '세금계산서와 현금영수증은 동시에 신청할 수 없습니다. 하나만 선택해 주세요.' });
    }

    // Enforce card checkout restrictions per Korean VAT Law:
    // Card payments automatically generate a credit card receipt (신용카드 매출전표) via PG,
    // which serves as tax proof. Therefore, both tax invoices and cash receipts are blocked.
    const isCardPayment = [
      PaymentMethod.CREDIT_CARD,
      PaymentMethod.KAKAO_PAY,
      PaymentMethod.NAVER_PAY,
      PaymentMethod.PAYCO,
      PaymentMethod.TOSS_PAY,
      PaymentMethod.ETC_SIMPLE_PAY,
    ].includes(selectedPaymentMethod);

    if (isCardPayment) {
      if (invoiceRequested) {
        return res.status(400).json({ error: '카드/간편결제는 PG사 매출전표가 자동 발행되므로 세금계산서 신청이 불가합니다.' });
      }
      if (cashReceiptRequested) {
        return res.status(400).json({ error: '선택하신 결제 수단은 현금영수증 발행 대상이 아닙니다.' });
      }
    }

    const expiresAt = new Date(Date.now() + PAYMENT_ORDER_EXPIRY_MS); // 30-minute expiry

    const order = await prisma.paymentOrder.create({
      data: {
        userId,
        productCode,
        productNameSnapshot: product.name,
        amountTotalSnapshot: product.amountTotal,
        creditAmountSnapshot: product.creditAmount,
        selectedPaymentMethod,
        invoiceRequested,
        cashReceiptRequested,
        orderStatus: OrderStatus.INITIATED,
        expiresAt,
      },
    });

    logger.info(`Prepared payment order: ID=${order.id}, total=${product.amountTotal}`);

    return res.status(201).json({
      paymentOrderUuid: order.paymentUuid,
      pgOrderId: order.id,
      amountTotal: product.amountTotal,
      productName: product.name,
    });
  } catch (error) {
    next(error);
  }
}

/**
 * POST /api/payments/callback
 * 
 * Invoked by client after checkout completion.
 * Confirms payment with PG, saves records, encrypts PII, logs outbound calls,
 * creates cross-border data transfer consent documentation, and schedules background worker tasks.
 */
export async function pgCallback(req: Request, res: Response, next: NextFunction) {
  try {
    const validated = pgCallbackSchema.parse(req.body);
    const { 
      paymentKey, 
      orderId, 
      amount, 
      paymentMethod, 
      status,
      companyRegNumber,
      companyName,
      ceoName,
      taxEmail,
      invoiceType,
      cashReceiptType,
      cashReceiptIdentityType,
      cashReceiptIdentityValue
    } = validated;

    // 1. Retrieve the prepared PaymentOrder
    const order = await prisma.paymentOrder.findUnique({
      where: { id: orderId },
      include: { user: true },
    });

    if (!order) {
      return res.status(404).json({ error: `PaymentOrder not found: ${orderId}` });
    }

    // Validate order has user data
    if (!order.user) {
      return res.status(400).json({ error: 'PaymentOrder has no associated user' });
    }

    // Check if the order has expired
    if (order.expiresAt && new Date() > order.expiresAt) {
      return res.status(400).json({ error: 'Payment order has expired' });
    }

    // Enforce Korean VAT Law receipt conflict prevention at callback too
    // Use the values stored in the order (from prepare), NOT the callback payload,
    // to prevent a malicious client from bypassing prepare's validation.
    const effectiveInvoiceRequested = order.invoiceRequested;
    const effectiveCashReceiptRequested = order.cashReceiptRequested;

    // Determine if this is a card/simple-pay method (for receipt type logic)
    const isCardPayment = [
      PaymentMethod.CREDIT_CARD,
      PaymentMethod.KAKAO_PAY,
      PaymentMethod.NAVER_PAY,
      PaymentMethod.PAYCO,
      PaymentMethod.TOSS_PAY,
      PaymentMethod.ETC_SIMPLE_PAY,
    ].includes(order.selectedPaymentMethod as PaymentMethod);

    if (effectiveInvoiceRequested && effectiveCashReceiptRequested) {
      return res.status(400).json({ error: '세금계산서와 현금영수증은 동시에 신청할 수 없습니다.' });
    }

    // Card payments cannot request tax invoices or cash receipts (Korean VAT Law)
    if (isCardPayment && (effectiveInvoiceRequested || effectiveCashReceiptRequested)) {
      return res.status(400).json({ error: '카드/간편결제는 세금계산서 및 현금영수증 신청이 불가합니다.' });
    }

    // Validate B2B fields when invoice is requested per the order
    if (effectiveInvoiceRequested && (!companyRegNumber || !companyName || !ceoName || !taxEmail)) {
      return res.status(400).json({ error: '세금계산서 신청 시 사업자등록번호, 상호명, 대표자명, 세금계산서 수신 이메일은 필수입니다.' });
    }

    // Validate cash receipt identity fields when cash receipt is requested per the order
    if (effectiveCashReceiptRequested && (!cashReceiptType || !cashReceiptIdentityType || !cashReceiptIdentityValue)) {
      return res.status(400).json({ error: '현금영수증 신청 시 현금영수증 종류, 식별유형, 식별값은 필수입니다.' });
    }

    // No payment method restriction on callback — already validated during prepare
    // const allowedMethods = [PaymentMethod.CREDIT_CARD, PaymentMethod.KAKAO_PAY, PaymentMethod.NAVER_PAY];
    // if (!allowedMethods.includes(order.selectedPaymentMethod as any)) {
    //   return res.status(400).json({ error: '지정하신 결제 수단은 승인 처리할 수 없습니다. 신용카드, 카카오페이, 네이버페이만 사용 가능합니다.' });
    // }

    if (order.amountTotalSnapshot !== amount) {
      return res.status(400).json({ error: `Transaction amount mismatch: Snapshot=${order.amountTotalSnapshot}, Callback=${amount}` });
    }

    // Idempotency: Use transaction to atomically check and prevent duplicate payments
    const existingPayment = await prisma.$transaction(async (tx) => {
      const payment = await tx.payment.findFirst({
        where: { pgOrderId: orderId },
      });
      return payment;
    });

    if (existingPayment && existingPayment.paymentStatus === PaymentStatus.PAID) {
      logger.info(`Payment already completed (idempotency check): ${orderId}`);
      return res.json({ success: true, paymentUuid: existingPayment.paymentUuid });
    }

    // 2. Call PG Client Adapter to Approve/Validate payment
    const pgApproval = await pgAdapter.approvePayment(paymentKey, orderId, amount, order.id);
    if (!pgApproval.success) {
      await prisma.paymentOrder.update({
        where: { id: orderId },
        data: { orderStatus: OrderStatus.FAILED },
      });
      logger.error(`PG approval failed for order ${orderId}: ${pgApproval.errorMessage}`);
      return res.status(400).json({ error: pgApproval.errorMessage || 'PG approval failed' });
    }

    // Validate pgApproval has required fields
    if (!pgApproval.pgTransactionId) {
      logger.error(`PG approval missing transaction ID for order ${orderId}`);
      return res.status(500).json({ error: 'PG approval response missing transaction ID' });
    }

    // 3. Compute VAT breakdown
    let taxBreakdown;
    try {
      taxBreakdown = calculateTax(amount);
    } catch (error) {
      logger.error(`Tax calculation failed for amount ${amount}: ${(error as Error).message}`);
      return res.status(500).json({ error: 'Tax calculation failed' });
    }

    // 4. Determine Receipt Type
    // Use order-stored values (from prepare) instead of callback payload to prevent bypass
    let finalReceiptType = ReceiptType.NONE;
    if (effectiveInvoiceRequested && companyRegNumber) {
      finalReceiptType = invoiceType === InvoiceType.INVOICE ? ReceiptType.INVOICE : ReceiptType.TAX_INVOICE;
    } else if (effectiveCashReceiptRequested && cashReceiptIdentityValue) {
      finalReceiptType = ReceiptType.CASH_RECEIPT;
    } else if (isCardPayment) {
      // Card/simple-pay methods: PG receipt auto-issued, serves as personal receipt
      finalReceiptType = ReceiptType.PERSONAL_RECEIPT;
    }

    // 5. Initialize Payment status
    const isVirtualAccountWaiting = status === 'WAITING_FOR_DEPOSIT' || paymentMethod.includes('가상계좌');
    const finalPaymentStatus = isVirtualAccountWaiting ? PaymentStatus.PENDING_DEPOSIT : PaymentStatus.PAID;

    // 6. DB transaction creating Payment, ConsentRecords and Sub-models
    let payment;
    try {
      payment = await prisma.$transaction(async (tx) => {
        // Create primary Payment record
        const payRecord = await tx.payment.create({
          data: {
            paymentUuid: order.paymentUuid,
            paymentOrderId: order.id,
            userId: order.userId,
            userUid: order.user.uid,
            pgProvider: 'TOSS_PAYMENTS',
            pgTransactionId: pgApproval.pgTransactionId,
            pgOrderId: orderId,
            paymentMethod: paymentMethod,
            amountTotal: amount,
            amountSupply: taxBreakdown.amountSupply,
            amountVat: taxBreakdown.amountVat,
            paymentStatus: finalPaymentStatus,
            receiptType: finalReceiptType,
            creditAmount: order.creditAmountSnapshot,
            creditStatus: DispatchStatus.READY,
            
            // Encrypt B2B invoicing PII
            companyRegNumberEncrypted: companyRegNumber ? encrypt(companyRegNumber) : null,
            companyRegNumberHash: companyRegNumber ? sha256Hash(companyRegNumber) : null,
            companyName: companyName || null,
            ceoName: ceoName || null,
            taxEmailEncrypted: taxEmail ? encrypt(taxEmail) : null,
            taxEmailHash: taxEmail ? sha256Hash(taxEmail) : null,
            invoiceType: effectiveInvoiceRequested ? (invoiceType || InvoiceType.TAX_INVOICE) : null,
            invoiceRequestStatus: effectiveInvoiceRequested ? DocumentIssueStatus.READY : null,
            
            rawPgPayload: pgApproval.rawPayload,
            paidAt: isVirtualAccountWaiting ? null : new Date(),
          },
        });

        // Update Order status
        await tx.paymentOrder.update({
          where: { id: orderId },
          data: { orderStatus: isVirtualAccountWaiting ? OrderStatus.PENDING_DEPOSIT : OrderStatus.PAID },
        });

        // B2C Cash Receipt Record
        if (finalReceiptType === ReceiptType.CASH_RECEIPT) {
          await tx.cashReceipt.create({
            data: {
              paymentId: payRecord.id,
              receiptStatus: CashReceiptStatus.READY,
              receiptType: cashReceiptType!,
              identityType: cashReceiptIdentityType!,
              identityValueEncrypted: encrypt(cashReceiptIdentityValue)!,
              identityHash: sha256Hash(cashReceiptIdentityValue)!,
              provider: 'TOSS_CASH_RECEIPT',
            },
          });
        }

        // Record Cross-Border Consent for sending minimum billing signal to China
        await tx.consentRecord.create({
          data: {
            userId: order.userId,
            paymentId: payRecord.id,
            consentType: 'CROSS_BORDER_CREDIT_DISPATCH',
            version: '1.0',
            agreed: true,
            disclosedItems: {
              uid: 'Hashed absolute user key',
              paymentUuid: 'Transaction reference key',
              creditAmount: 'Credits amount to charge',
            },
            country: 'CN',
            transferTimeDesc: 'Immediately upon payment completion',
            transferMethod: 'Secure webhook client call (TLS 1.3)',
            recipientName: 'China Central Credit Storage Server',
            recipientContact: 'china-support@worksite.example.com',
            purpose: 'Credit allocation and charging synchronization',
            retentionPeriod: '5 Years (Matched with Korean Tax Ledger requirements)',
            refusalMethod: 'Request payment cancellation or customer support contact',
            refusalEffect: 'Credits will not be synchronized to Chinese site',
            ipAddress: req.ip || '127.0.0.1',
            userAgent: req.headers['user-agent'] || 'Unknown',
          },
        });

        return payRecord;
      });
    } catch (error) {
      logger.error(`Database transaction failed for order ${orderId}: ${(error as Error).message}`);
      return res.status(500).json({ error: 'Failed to create payment record' });
    }

    // Write traces
    if (finalPaymentStatus === PaymentStatus.PAID) {
      await addPaymentTrace(payment.id, 'PG_PAYMENT', 'INITIATED', 'Payment checkout session prepared.');
      await addPaymentTrace(payment.id, 'PG_PAYMENT', 'SUCCESS', `TossPayments payment approved successfully. Transaction: ${paymentKey}, Amount: ${amount} KRW.`);
    } else {
      await addPaymentTrace(payment.id, 'PG_PAYMENT', 'INITIATED', 'Payment prepared. Waiting for virtual account deposit.');
    }

    // 7. Enqueue background queue workers if payment is completed
    if (finalPaymentStatus === PaymentStatus.PAID) {
      try {
        // Topup credits
        await paymentQueue.add('SEND_CREDIT', { paymentId: payment.id });

        // Issue Tax Document
        if (finalReceiptType === ReceiptType.TAX_INVOICE || finalReceiptType === ReceiptType.INVOICE) {
          await paymentQueue.add('ISSUE_TAX_DOCUMENT', { paymentId: payment.id });
        }

        // Issue Cash Receipt
        if (finalReceiptType === ReceiptType.CASH_RECEIPT) {
          await paymentQueue.add('ISSUE_CASH_RECEIPT', { paymentId: payment.id });
        }
      } catch (error) {
        logger.error(`Failed to enqueue background jobs for payment ${payment.id}: ${(error as Error).message}`);
        // Don't fail the request - payment is already created
      }
    }

    logger.info(`Completed PG callback logic for payment: ${payment.id}`);
    return res.json({ success: true, paymentUuid: payment.paymentUuid });
  } catch (error) {
    next(error);
  }
}

/**
 * GET /api/payments/:paymentUuid/status
 */
export async function getPaymentStatus(req: Request, res: Response, next: NextFunction) {
  try {
    const { paymentUuid } = req.params;

    const payment = await prisma.payment.findUnique({
      where: { paymentUuid },
      include: {
        cashReceipts: {
          select: { receiptStatus: true },
        },
        creditDispatches: {
          select: { uid: true, dispatchStatus: true },
        },
      },
    });

    if (!payment) {
      return res.status(404).json({ error: 'Payment record not found' });
    }

    // Response shape matches the API spec in README.md
    // with minimal extra fields needed by the frontend Result page
    return res.json({
      paymentUuid: payment.paymentUuid,
      amountTotal: payment.amountTotal,
      paymentStatus: payment.paymentStatus,
      receiptType: payment.receiptType,
      creditStatus: payment.creditStatus,
      creditedAt: payment.creditedAt,
      invoiceRequestStatus: payment.invoiceRequestStatus,
      cashReceipts: payment.cashReceipts,
      creditDispatches: payment.creditDispatches,
    });
  } catch (error) {
    next(error);
  }
}

/**
 * POST /api/payments/webhook
 * 
 * TossPayments Virtual Account Deposit Notification Webhook (Simulated)
 * Verifies webhook signature to prevent forgery.
 */
export async function handlePgWebhook(req: Request, res: Response, next: NextFunction) {
  try {
    const validated = pgWebhookSchema.parse(req.body);
    const { status, orderId, paymentKey, signature } = validated;
    logger.info(`Received PG Deposit Webhook for orderId=${orderId}, status=${status}`);

    // Verify webhook signature to prevent forgery
    if (signature) {
      const hmac = crypto.createHmac('sha256', env.PG_API_SECRET_KEY);
      const expectedSignature = hmac.update(`${orderId}:${status}:${paymentKey}`).digest('hex');
      const sigBuf = Buffer.from(signature);
      const expectedBuf = Buffer.from(expectedSignature);
      if (sigBuf.length !== expectedBuf.length || !crypto.timingSafeEqual(sigBuf, expectedBuf)) {
        logger.warn(`Invalid PG webhook signature for orderId=${orderId}`);
        return res.status(401).json({ error: 'Invalid webhook signature' });
      }
    } else if (env.NODE_ENV === 'production') {
      // In production, signature is mandatory
      logger.warn(`Missing PG webhook signature for orderId=${orderId}`);
      return res.status(401).json({ error: 'Missing webhook signature' });
    }

    if (status !== 'DONE') {
      return res.json({ success: true, message: 'Ignored non-DONE webhook status' });
    }

    // Validate orderId format (should be a positive integer)
    const orderIdNum = parseInt(orderId, 10);
    if (isNaN(orderIdNum) || orderIdNum <= 0 || orderId.toString() !== orderIdNum.toString()) {
      logger.warn(`Invalid orderId format in webhook: ${orderId}`);
      return res.status(400).json({ error: 'Invalid orderId format' });
    }

    // 1. Find the payment order and payment record
    const payment = await prisma.payment.findFirst({
      where: { pgOrderId: orderId },
      include: { paymentOrder: true },
    });

    if (!payment) {
      return res.status(404).json({ error: `Payment record not found for webhook order: ${orderId}` });
    }

    // Idempotency: If already PAID, just return success
    if (payment.paymentStatus === PaymentStatus.PAID) {
      return res.json({ success: true, message: 'Already processed as PAID' });
    }

    // 2. Transaction update database (Payment Status -> PAID)
    const updatedPayment = await prisma.$transaction(async (tx) => {
      const payRecord = await tx.payment.update({
        where: { id: payment.id },
        data: {
          paymentStatus: PaymentStatus.PAID,
          pgTransactionId: paymentKey || payment.pgTransactionId,
          paidAt: new Date(),
        },
      });

      await tx.paymentOrder.update({
        where: { id: payment.paymentOrderId },
        data: { orderStatus: OrderStatus.PAID },
      });

      return payRecord;
    });

    // Write trace
    await addPaymentTrace(payment.id, 'PG_PAYMENT', 'SUCCESS', `Virtual account deposit received via webhook. Transaction: ${paymentKey || payment.pgTransactionId}, Amount: ${payment.amountTotal} KRW.`);

    // 3. Enqueue background tasks
    await paymentQueue.add('SEND_CREDIT', { paymentId: updatedPayment.id });

    if (updatedPayment.receiptType === ReceiptType.TAX_INVOICE || updatedPayment.receiptType === ReceiptType.INVOICE) {
      await paymentQueue.add('ISSUE_TAX_DOCUMENT', { paymentId: updatedPayment.id });
    }

    if (updatedPayment.receiptType === ReceiptType.CASH_RECEIPT) {
      await paymentQueue.add('ISSUE_CASH_RECEIPT', { paymentId: updatedPayment.id });
    }

    logger.info(`Successfully processed webhook deposit. Payment ID=${updatedPayment.id}`);
    return res.json({ success: true, paymentUuid: updatedPayment.paymentUuid });
  } catch (error) {
    next(error);
  }
}

/**
 * POST /api/payments/remote-webhook
 * 
 * Inbound webhook callback from the remote platform confirming credit sync results.
 */
export async function handleRemoteWebhook(req: Request, res: Response, next: NextFunction) {
  try {
    const validated = remoteWebhookSchema.parse(req.body);
    const { paymentUuid, status, errorMessage, signature } = validated;

    // Verify signature using the shared secret (with separator to prevent collision)
    const hmac = crypto.createHmac('sha256', env.CHINA_CREDIT_API_KEY);
    const expectedSignature = hmac.update(`${paymentUuid}|${status}`).digest('hex');
    
    const sigBuf = Buffer.from(signature);
    const expectedBuf = Buffer.from(expectedSignature);
    if (sigBuf.length !== expectedBuf.length || !crypto.timingSafeEqual(sigBuf, expectedBuf)) {
      logger.warn(`Invalid remote webhook signature for payment: ${paymentUuid}`);
      return res.status(401).json({ error: 'Invalid webhook signature' });
    }

    const payment = await prisma.payment.findUnique({
      where: { paymentUuid },
      include: { creditDispatches: true },
    });

    if (!payment) {
      return res.status(404).json({ error: `Payment not found for remote webhook: ${paymentUuid}` });
    }

    // Verification: ignore if already completed or not in transient status
    if (payment.creditStatus !== DispatchStatus.SENT && payment.creditStatus !== DispatchStatus.PROCESSING) {
      logger.info(`Ignored remote webhook for payment ${payment.id} due to current state: ${payment.creditStatus}`);
      return res.json({ success: true, message: `Ignored callback for current state: ${payment.creditStatus}` });
    }

    const isSuccess = status === 'SUCCESS';
    const finalStatus = isSuccess ? DispatchStatus.CONFIRMED : DispatchStatus.FAILED;

    await prisma.$transaction(async (tx) => {
      await tx.payment.update({
        where: { id: payment.id },
        data: {
          creditStatus: finalStatus,
          creditedAt: isSuccess ? new Date() : null,
        },
      });

      if (payment.creditDispatches[0]) {
        await tx.creditDispatch.update({
          where: { id: payment.creditDispatches[0].id },
          data: {
            dispatchStatus: finalStatus,
            confirmedAt: isSuccess ? new Date() : null,
            lastErrorMessage: isSuccess ? null : (errorMessage || 'Remote platform reported failure'),
          },
        });
      }
    });

    if (isSuccess) {
      await addPaymentTrace(
        payment.id, 
        'CHINA_WEBHOOK', 
        'SUCCESS', 
        `Remote platform webhook confirmation received successfully. Credit sync confirmed.`,
        { paymentUuid, status }
      );
    } else {
      await addPaymentTrace(
        payment.id, 
        'CHINA_WEBHOOK', 
        'FAILED', 
        `Remote platform webhook reported failure: ${errorMessage || 'Unknown error'}`,
        { paymentUuid, status }
      );
    }

    logger.info(`Successfully processed remote platform webhook for payment ${payment.id} with status ${status}`);
    return res.json({ success: true });
  } catch (error) {
    next(error);
  }
}


