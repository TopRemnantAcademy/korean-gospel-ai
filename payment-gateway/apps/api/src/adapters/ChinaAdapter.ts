import axios from 'axios';
import { env } from '../config/env';
import { logExternalCall } from '../utils/externalCallLogger';
import logger from '../utils/logger';

export interface CreditDispatchResult {
  success: boolean;
  requestPayload: any;
  responsePayload: any;
  errorMessage?: string;
}

export class ChinaCreditAdapter {
  private readonly apiUrl: string;
  private readonly apiKey: string;

  constructor() {
    this.apiUrl = env.CHINA_CREDIT_API_URL;
    this.apiKey = env.CHINA_CREDIT_API_KEY;
  }

  async sendCredit(params: {
    paymentId: string;
    uid: string;
    creditedAmount: number;
    paymentRef: string;
  }): Promise<CreditDispatchResult> {
    const url = `${this.apiUrl}/allocate`;
    const headers = {
      'X-Partner-Auth-Key': this.apiKey,
      'Content-Type': 'application/json',
    };
    
    // Strict requirement: uid, payment_ref, credited_amount only. No PII.
    const body = {
      uid: params.uid,
      credited_amount: params.creditedAmount,
      payment_ref: params.paymentRef,
      action: 'ALLOCATE',
    };

    logger.info(`Sending credit to Chinese Server: uid=${params.uid.slice(0, 8)}..., amount=${params.creditedAmount}`, { paymentId: params.paymentId });

    // Mock mode controlled by environment variable
    if (env.MOCK_CHINA_API) {
      const mockResponse = {
        code: 'SUCCESS',
        message: 'Credit allocated successfully',
        transaction_id: `cn_credit_tx_${Date.now()}`,
        timestamp: Date.now(),
      };

      await logExternalCall({
        domain: 'CHINA_INTEGRATION_SERVER',
        direction: 'OUTBOUND',
        relatedPaymentId: params.paymentId,
        targetUrl: url,
        requestHeaders: headers,
        requestBody: body,
        responseStatus: 200,
        responseBody: mockResponse,
        success: true,
      });

      return {
        success: true,
        requestPayload: body,
        responsePayload: mockResponse,
      };
    }

    try {
      const response = await axios.post(url, body, { headers, timeout: 5000 });
      
      await logExternalCall({
        domain: 'CHINA_INTEGRATION_SERVER',
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
        requestPayload: body,
        responsePayload: response.data,
      };
    } catch (error: any) {
      const errRes = error.response;
      const errMsg = errRes?.data?.message || error.message;

      await logExternalCall({
        domain: 'CHINA_INTEGRATION_SERVER',
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
        requestPayload: body,
        responsePayload: errRes?.data || null,
        errorMessage: errMsg,
      };
    }
  }

  async reverseCredit(params: {
    paymentId: string;
    refundId: string;
    uid: string;
    creditedAmount: number;
    paymentRef: string;
  }): Promise<CreditDispatchResult> {
    const url = `${this.apiUrl}/reverse`;
    const headers = {
      'X-Partner-Auth-Key': this.apiKey,
      'Content-Type': 'application/json',
    };
    
    // Credit reversal payload
    const body = {
      uid: params.uid,
      credited_amount: params.creditedAmount,
      payment_ref: params.paymentRef,
      action: 'REVERSE',
    };

    logger.info(`Reversing credit on Chinese Server: uid=${params.uid.slice(0, 8)}..., amount=${params.creditedAmount}`, { paymentId: params.paymentId });

    // Mock mode controlled by environment variable
    if (env.MOCK_CHINA_API) {
      const mockResponse = {
        code: 'SUCCESS',
        message: 'Credit reversed successfully',
        transaction_id: `cn_reversal_tx_${Date.now()}`,
        timestamp: Date.now(),
      };

      await logExternalCall({
        domain: 'CHINA_INTEGRATION_SERVER',
        direction: 'OUTBOUND',
        relatedPaymentId: params.paymentId,
        relatedRefundId: params.refundId,
        targetUrl: url,
        requestHeaders: headers,
        requestBody: body,
        responseStatus: 200,
        responseBody: mockResponse,
        success: true,
      });

      return {
        success: true,
        requestPayload: body,
        responsePayload: mockResponse,
      };
    }

    try {
      const response = await axios.post(url, body, { headers, timeout: 5000 });
      
      await logExternalCall({
        domain: 'CHINA_INTEGRATION_SERVER',
        direction: 'OUTBOUND',
        relatedPaymentId: params.paymentId,
        relatedRefundId: params.refundId,
        targetUrl: url,
        requestHeaders: headers,
        requestBody: body,
        responseStatus: response.status,
        responseBody: response.data,
        success: true,
      });

      return {
        success: true,
        requestPayload: body,
        responsePayload: response.data,
      };
    } catch (error: any) {
      const errRes = error.response;
      const errMsg = errRes?.data?.message || error.message;

      await logExternalCall({
        domain: 'CHINA_INTEGRATION_SERVER',
        direction: 'OUTBOUND',
        relatedPaymentId: params.paymentId,
        relatedRefundId: params.refundId,
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
        requestPayload: body,
        responsePayload: errRes?.data || null,
        errorMessage: errMsg,
      };
    }
  }
}
export default ChinaCreditAdapter;
