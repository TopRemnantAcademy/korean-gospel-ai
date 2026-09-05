import axios from 'axios';
import { env } from '../config/env';
import { logExternalCall } from '../utils/externalCallLogger';
import logger from '../utils/logger';

export interface TaxIssueResult {
  success: boolean;
  providerDocumentId?: string;
  errorMessage?: string;
}

export class TaxInvoiceAdapter {
  private readonly apiKey: string;
  private readonly baseUrl = 'https://api.taxservice.co.kr/v1'; // Simulated Tax Invoice API

  constructor() {
    this.apiKey = env.TAX_INVOICE_API_KEY;
  }

  async issueTaxInvoice(params: {
    paymentId: string;
    companyRegNumber: string;
    companyName: string;
    ceoName: string;
    taxEmail: string;
    amountSupply: number;
    amountVat: number;
  }): Promise<TaxIssueResult> {
    const url = `${this.baseUrl}/tax-invoices/issue`;
    const headers = {
      Authorization: `Bearer ${this.apiKey}`,
      'Content-Type': 'application/json',
    };
    const body = {
      type: 'TAX_INVOICE',
      paymentId: params.paymentId,
      corporateNumber: params.companyRegNumber,
      corporateName: params.companyName,
      ceoName: params.ceoName,
      email: params.taxEmail,
      supplyAmount: params.amountSupply,
      vat: params.amountVat,
      totalAmount: params.amountSupply + params.amountVat,
    };

    logger.info(`Tax Invoice request: ${params.companyRegNumber}`, { paymentId: params.paymentId });

    if (this.apiKey === 'tax_api_auth_secret_key_1234') {
      const mockDocId = `MOCK_TAX_DOC_${Date.now()}`;
      await logExternalCall({
        domain: 'TAX_INVOICE_PROVIDER',
        direction: 'OUTBOUND',
        relatedPaymentId: params.paymentId,
        targetUrl: url,
        requestHeaders: headers,
        requestBody: body,
        responseStatus: 200,
        responseBody: { code: 'SUCCESS', message: 'Issued successfully', docId: mockDocId },
        success: true,
      });

      return {
        success: true,
        providerDocumentId: mockDocId,
      };
    }

    try {
      const response = await axios.post(url, body, { headers, timeout: 5000 });
      await logExternalCall({
        domain: 'TAX_INVOICE_PROVIDER',
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
        providerDocumentId: response.data.docId,
      };
    } catch (error: any) {
      const errRes = error.response;
      const errMsg = errRes?.data?.message || error.message;

      await logExternalCall({
        domain: 'TAX_INVOICE_PROVIDER',
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

  async issueInvoice(params: {
    paymentId: string;
    companyRegNumber: string;
    companyName: string;
    ceoName: string;
    taxEmail: string;
    amountTotal: number;
  }): Promise<TaxIssueResult> {
    // Non-taxable B2B (면세 계산서)
    const url = `${this.baseUrl}/invoices/issue`;
    const headers = {
      Authorization: `Bearer ${this.apiKey}`,
      'Content-Type': 'application/json',
    };
    const body = {
      type: 'INVOICE',
      paymentId: params.paymentId,
      corporateNumber: params.companyRegNumber,
      corporateName: params.companyName,
      ceoName: params.ceoName,
      email: params.taxEmail,
      supplyAmount: params.amountTotal,
      vat: 0,
      totalAmount: params.amountTotal,
    };

    logger.info(`Invoice request (Tax-free): ${params.companyRegNumber}`, { paymentId: params.paymentId });

    if (this.apiKey === 'tax_api_auth_secret_key_1234') {
      const mockDocId = `MOCK_BILL_DOC_${Date.now()}`;
      await logExternalCall({
        domain: 'TAX_INVOICE_PROVIDER',
        direction: 'OUTBOUND',
        relatedPaymentId: params.paymentId,
        targetUrl: url,
        requestHeaders: headers,
        requestBody: body,
        responseStatus: 200,
        responseBody: { code: 'SUCCESS', message: 'Issued tax-exempt document successfully', docId: mockDocId },
        success: true,
      });

      return {
        success: true,
        providerDocumentId: mockDocId,
      };
    }

    try {
      const response = await axios.post(url, body, { headers, timeout: 5000 });
      await logExternalCall({
        domain: 'TAX_INVOICE_PROVIDER',
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
        providerDocumentId: response.data.docId,
      };
    } catch (error: any) {
      const errRes = error.response;
      const errMsg = errRes?.data?.message || error.message;

      await logExternalCall({
        domain: 'TAX_INVOICE_PROVIDER',
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

  async cancelOrAdjustDocument(
    paymentId: string,
    providerDocumentId: string,
    adjustAmount: number, // Negative for cancellation/refund
    reason: string
  ): Promise<TaxIssueResult> {
    const url = `${this.baseUrl}/documents/${providerDocumentId}/adjust`;
    const headers = {
      Authorization: `Bearer ${this.apiKey}`,
      'Content-Type': 'application/json',
    };
    const body = {
      adjustAmount,
      reason,
    };

    logger.info(`Tax Document cancellation: ${providerDocumentId}`, { paymentId, adjustAmount });

    if (this.apiKey === 'tax_api_auth_secret_key_1234') {
      await logExternalCall({
        domain: 'TAX_INVOICE_PROVIDER',
        direction: 'OUTBOUND',
        relatedPaymentId: paymentId,
        targetUrl: url,
        requestHeaders: headers,
        requestBody: body,
        responseStatus: 200,
        responseBody: { code: 'SUCCESS', message: 'Adjusted/Cancelled document successfully' },
        success: true,
      });

      return {
        success: true,
      };
    }

    try {
      const response = await axios.post(url, body, { headers, timeout: 5000 });
      await logExternalCall({
        domain: 'TAX_INVOICE_PROVIDER',
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
      };
    } catch (error: any) {
      const errRes = error.response;
      const errMsg = errRes?.data?.message || error.message;

      await logExternalCall({
        domain: 'TAX_INVOICE_PROVIDER',
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
        errorMessage: errMsg,
      };
    }
  }
}
export default TaxInvoiceAdapter;
