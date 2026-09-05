import { CashReceiptIdentityType, CashReceiptType } from '@gospel-pay/shared';
import axios from 'axios';
import { env } from '../config/env';
import { logExternalCall } from '../utils/externalCallLogger';
import logger from '../utils/logger';

export interface CashReceiptResult {
  success: boolean;
  providerReceiptId?: string;
  errorMessage?: string;
}

export class CashReceiptAdapter {
  private readonly secretKey: string;
  private readonly baseUrl = 'https://api.tosspayments.com/v1';

  constructor() {
    this.secretKey = env.PG_API_SECRET_KEY;
  }

  async issueCashReceipt(params: {
    paymentId: string;
    amount: number;
    receiptType: CashReceiptType;
    identityType: CashReceiptIdentityType;
    identityValue: string;
  }): Promise<CashReceiptResult> {
    const url = `${this.baseUrl}/cash-receipts`;
    const headers = {
      Authorization: `Basic ${Buffer.from(this.secretKey + ':').toString('base64')}`,
      'Content-Type': 'application/json',
    };
    
    // map type to PG values
    const body = {
      amount: params.amount,
      orderId: `CR_${params.paymentId.slice(0, 8)}_${Date.now()}`,
      orderName: 'Cash Receipt Issuance',
      customerIdentityNumber: params.identityValue,
      type: params.receiptType === CashReceiptType.INCOME_DEDUCTION ? '소득공제' : '지출증빙',
    };

    logger.info(`Cash Receipt Request for Payment: ${params.paymentId}`, {
      type: params.receiptType,
      identityType: params.identityType,
    });

    if (this.secretKey === 'test_gsk_5yZ2Q60gzObZ1Q075zX3V7gK0123') {
      const mockReceiptId = `MOCK_CASH_REC_${Date.now()}`;
      await logExternalCall({
        domain: 'TOSS_CASH_RECEIPT',
        direction: 'OUTBOUND',
        relatedPaymentId: params.paymentId,
        targetUrl: url,
        requestHeaders: headers,
        requestBody: body,
        responseStatus: 200,
        responseBody: { receiptKey: mockReceiptId, orderId: body.orderId, status: 'IN_PROGRESS' },
        success: true,
      });

      return {
        success: true,
        providerReceiptId: mockReceiptId,
      };
    }

    try {
      const response = await axios.post(url, body, { headers, timeout: 5000 });
      await logExternalCall({
        domain: 'TOSS_CASH_RECEIPT',
        direction: 'OUTBOUND',
        relatedPaymentId: params.paymentId,
        targetUrl: url,
        requestHeaders: headers,
        requestBody: body,
        responseStatus: response.status,
        responseBody: response.data,
        success: true,
      });

      return {
        success: true,
        providerReceiptId: response.data.receiptKey,
      };
    } catch (error: any) {
      const errRes = error.response;
      const errMsg = errRes?.data?.message || error.message;

      await logExternalCall({
        domain: 'TOSS_CASH_RECEIPT',
        direction: 'OUTBOUND',
        relatedPaymentId: params.paymentId,
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
        errorMessage: errMsg,
      };
    }
  }

  async cancelCashReceipt(params: {
    paymentId: string;
    providerReceiptId: string;
    amount: number;
  }): Promise<CashReceiptResult> {
    const url = `${this.baseUrl}/cash-receipts/${params.providerReceiptId}/cancel`;
    const headers = {
      Authorization: `Basic ${Buffer.from(this.secretKey + ':').toString('base64')}`,
      'Content-Type': 'application/json',
    };
    const body = {
      amount: params.amount,
    };

    logger.info(`Cash Receipt Cancellation request: ${params.providerReceiptId}`, { paymentId: params.paymentId });

    if (this.secretKey === 'test_gsk_5yZ2Q60gzObZ1Q075zX3V7gK0123') {
      await logExternalCall({
        domain: 'TOSS_CASH_RECEIPT',
        direction: 'OUTBOUND',
        relatedPaymentId: params.paymentId,
        targetUrl: url,
        requestHeaders: headers,
        requestBody: body,
        responseStatus: 200,
        responseBody: { receiptKey: params.providerReceiptId, status: 'CANCELED' },
        success: true,
      });

      return {
        success: true,
      };
    }

    try {
      const response = await axios.post(url, body, { headers, timeout: 5000 });
      await logExternalCall({
        domain: 'TOSS_CASH_RECEIPT',
        direction: 'OUTBOUND',
        relatedPaymentId: params.paymentId,
        targetUrl: url,
        requestHeaders: headers,
        requestBody: body,
        responseStatus: response.status,
        responseBody: response.data,
        success: true,
      });

      return {
        success: true,
      };
    } catch (error: any) {
      const errRes = error.response;
      const errMsg = errRes?.data?.message || error.message;

      await logExternalCall({
        domain: 'TOSS_CASH_RECEIPT',
        direction: 'OUTBOUND',
        relatedPaymentId: params.paymentId,
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
        errorMessage: errMsg,
      };
    }
  }
}
export default CashReceiptAdapter;
