import { PaymentMethod } from '@gospel-pay/shared';
import axios from 'axios';
import { env } from '../config/env';
import { logExternalCall } from '../utils/externalCallLogger';
import logger from '../utils/logger';

export interface PgPrepareResult {
  pgOrderId: string;
  amount: number;
}

export interface PgApproveResult {
  success: boolean;
  pgTransactionId: string;
  pgOrderId: string;
  paidAt: Date;
  rawPayload: any;
  errorMessage?: string;
}

export interface PgCancelResult {
  success: boolean;
  pgRefundId?: string;
  rawPayload: any;
  errorMessage?: string;
}

export interface PgClientInterface {
  preparePayment(orderId: string, amount: number): Promise<PgPrepareResult>;
  verifyCallback(payload: any): Promise<boolean>;
  approvePayment(paymentKey: string, orderId: string, amount: number, paymentOrderId?: string): Promise<PgApproveResult>;
  cancelPayment(paymentKey: string, reason: string, paymentOrderId?: string): Promise<PgCancelResult>;
  refundPayment(paymentKey: string, amount: number, reason: string, refundAccount?: any, paymentOrderId?: string): Promise<PgCancelResult>;
  getSupportedMethods(): PaymentMethod[];
}

export class TossPaymentsAdapter implements PgClientInterface {
  private readonly secretKey: string;
  private readonly baseUrl = 'https://api.tosspayments.com/v1';

  constructor() {
    this.secretKey = env.PG_API_SECRET_KEY;
  }

  getSupportedMethods(): PaymentMethod[] {
    // TossPayments actual supported methods (Sanitized to Credit Card, KakaoPay, NaverPay)
    return [
      PaymentMethod.CREDIT_CARD,
      PaymentMethod.KAKAO_PAY,
      PaymentMethod.NAVER_PAY,
    ];
  }

  async preparePayment(orderId: string, amount: number): Promise<PgPrepareResult> {
    // TossPayments doesn't require a prep request for client-side SDKs, 
    // but we simulate returning checkout parameters.
    return {
      pgOrderId: orderId,
      amount,
    };
  }

  async verifyCallback(payload: any): Promise<boolean> {
    // In sandbox, we check validation. Real production checks signature headers.
    if (!payload.paymentKey || !payload.orderId || !payload.amount) {
      return false;
    }
    return true;
  }

  async approvePayment(paymentKey: string, orderId: string, amount: number, paymentId?: string): Promise<PgApproveResult> {
    const url = `${this.baseUrl}/payments/confirm`;
    const headers = {
      Authorization: `Basic ${Buffer.from(this.secretKey + ':').toString('base64')}`,
      'Content-Type': 'application/json',
    };
    const body = { paymentKey, orderId, amount };

    logger.info(`PG Approve Request: ${url}`, { orderId, amount });

    // For sandbox testing, if the secret is "test_gsk_5yZ2Q60gzObZ1Q075zX3V7gK0123", we simulate success
    if (this.secretKey === 'test_gsk_5yZ2Q60gzObZ1Q075zX3V7gK0123') {
      const mockPayload = {
        paymentKey,
        orderId,
        amount,
        status: 'DONE',
        transactionId: `mock_tx_${Date.now()}`,
        approvedAt: new Date().toISOString(),
        method: '카드',
      };
      
      await logExternalCall({
        domain: 'TOSS_PAYMENTS',
        direction: 'OUTBOUND',
        relatedPaymentId: paymentId,
        targetUrl: url,
        requestHeaders: headers,
        requestBody: body,
        responseStatus: 200,
        responseBody: mockPayload,
        success: true,
      });

      return {
        success: true,
        pgTransactionId: mockPayload.transactionId,
        pgOrderId: orderId,
        paidAt: new Date(mockPayload.approvedAt),
        rawPayload: mockPayload,
      };
    }

    try {
      const response = await axios.post(url, body, { headers, timeout: 10000 });
      
      await logExternalCall({
        domain: 'TOSS_PAYMENTS',
        direction: 'OUTBOUND',
        relatedPaymentId: paymentId,
        targetUrl: url,
        requestHeaders: headers,
        requestBody: body,
        responseStatus: response.status,
        responseBody: response.data,
        success: true,
      });

      return {
        success: true,
        pgTransactionId: response.data.transactionKey || response.data.paymentKey,
        pgOrderId: response.data.orderId,
        paidAt: new Date(response.data.approvedAt),
        rawPayload: response.data,
      };
    } catch (error: any) {
      const errRes = error.response;
      const errMsg = errRes?.data?.message || error.message;

      await logExternalCall({
        domain: 'TOSS_PAYMENTS',
        direction: 'OUTBOUND',
        relatedPaymentId: paymentId,
        targetUrl: url,
        requestHeaders: headers,
        requestBody: body,
        responseStatus: errRes?.status || 500,
        responseBody: errRes?.data || null,
        success: false,
        errorMessage: errMsg,
      });

      return {
        success: false,
        pgTransactionId: '',
        pgOrderId: orderId,
        paidAt: new Date(),
        rawPayload: errRes?.data || null,
        errorMessage: errMsg,
      };
    }
  }

  async cancelPayment(paymentKey: string, reason: string, paymentId?: string): Promise<PgCancelResult> {
    return this.refundPayment(paymentKey, 0, reason, undefined, paymentId);
  }

  async refundPayment(
    paymentKey: string,
    amount: number,
    reason: string,
    refundAccount?: { bankCode: string; accountNumber: string; accountHolder: string },
    paymentId?: string
  ): Promise<PgCancelResult> {
    const url = `${this.baseUrl}/payments/${paymentKey}/cancel`;
    const headers = {
      Authorization: `Basic ${Buffer.from(this.secretKey + ':').toString('base64')}`,
      'Content-Type': 'application/json',
    };
    
    const body: any = { cancelReason: reason };
    if (amount > 0) {
      body.cancelAmount = amount;
    }
    if (refundAccount) {
      body.refundReceiveAccount = {
        bank: refundAccount.bankCode,
        accountNumber: refundAccount.accountNumber,
        holderName: refundAccount.accountHolder,
      };
    }

    logger.info(`PG Refund Request: ${url}`, { paymentKey, amount, reason });

    if (this.secretKey === 'test_gsk_5yZ2Q60gzObZ1Q075zX3V7gK0123') {
      const mockPayload = {
        paymentKey,
        status: amount === 0 ? 'CANCELED' : 'PARTIALLY_CANCELED',
        transactionId: `mock_tx_${Date.now()}`,
        canceledAt: new Date().toISOString(),
        cancels: [{ cancelAmount: amount, cancelReason: reason }],
      };

      await logExternalCall({
        domain: 'TOSS_PAYMENTS',
        direction: 'OUTBOUND',
        relatedPaymentId: paymentId,
        targetUrl: url,
        requestHeaders: headers,
        requestBody: body,
        responseStatus: 200,
        responseBody: mockPayload,
        success: true,
      });

      return {
        success: true,
        pgRefundId: `mock_ref_${Date.now()}`,
        rawPayload: mockPayload,
      };
    }

    try {
      const response = await axios.post(url, body, { headers, timeout: 10000 });

      await logExternalCall({
        domain: 'TOSS_PAYMENTS',
        direction: 'OUTBOUND',
        relatedPaymentId: paymentId,
        targetUrl: url,
        requestHeaders: headers,
        requestBody: body,
        responseStatus: response.status,
        responseBody: response.data,
        success: true,
      });

      return {
        success: true,
        pgRefundId: response.data.cancels?.[0]?.transactionKey || `ref_${Date.now()}`,
        rawPayload: response.data,
      };
    } catch (error: any) {
      const errRes = error.response;
      const errMsg = errRes?.data?.message || error.message;

      await logExternalCall({
        domain: 'TOSS_PAYMENTS',
        direction: 'OUTBOUND',
        relatedPaymentId: paymentId,
        targetUrl: url,
        requestHeaders: headers,
        requestBody: body,
        responseStatus: errRes?.status || 500,
        responseBody: errRes?.data || null,
        success: false,
        errorMessage: errMsg,
      });

      return {
        success: false,
        rawPayload: errRes?.data || null,
        errorMessage: errMsg,
      };
    }
  }
}
