import prisma from '../repositories/db';
import logger from './logger';

export interface ExternalLogParams {
  domain: string;
  direction: 'INBOUND' | 'OUTBOUND';
  relatedPaymentId?: string;
  relatedRefundId?: string;
  requestId?: string;
  targetUrl: string;
  requestHeaders?: any;
  requestBody?: any;
  responseStatus?: number;
  responseBody?: any;
  success: boolean;
  errorMessage?: string;
}

export async function logExternalCall(params: ExternalLogParams): Promise<void> {
  try {
    // Mask sensitive parameters in logs
    const maskedRequestBody = maskData(params.requestBody);
    const maskedResponseBody = maskData(params.responseBody);

    await prisma.externalCallLog.create({
      data: {
        domain: params.domain,
        direction: params.direction,
        relatedPaymentId: params.relatedPaymentId || null,
        relatedRefundId: params.relatedRefundId || null,
        requestId: params.requestId || null,
        targetUrl: params.targetUrl,
        requestHeaders: params.requestHeaders ? maskHeaders(params.requestHeaders) : null,
        requestBody: maskedRequestBody ? JSON.parse(JSON.stringify(maskedRequestBody)) : null,
        responseStatus: params.responseStatus || null,
        responseBody: maskedResponseBody ? JSON.parse(JSON.stringify(maskedResponseBody)) : null,
        success: params.success,
        errorMessage: params.errorMessage || null,
      },
    });
  } catch (error) {
    logger.error(`Failed to log external call to DB: ${(error as Error).message}`, { params });
  }
}

/**
 * Mask PII and sensitive credentials from external call logs to ensure compliance with privacy laws
 */
function maskData(data: any): any {
  if (!data) return data;
  try {
    const copy = JSON.parse(JSON.stringify(data));
    const sensitiveKeys = [
      'phone', 'email', 'companyRegNumber', 'companyRegNumberEncrypted',
      'taxEmail', 'identityValue', 'identityValueEncrypted',
      'refundAccountNumber', 'refundAccountNumberEncrypted', 'accountNumber'
    ];

    const traverse = (obj: any) => {
      for (const key in obj) {
        if (typeof obj[key] === 'object' && obj[key] !== null) {
          traverse(obj[key]);
        } else if (sensitiveKeys.includes(key) && typeof obj[key] === 'string') {
          obj[key] = '***MASKED_IN_LOG***';
        }
      }
    };

    traverse(copy);
    return copy;
  } catch (error) {
    logger.warn('Failed to mask data for logging, returning original data', { error: (error as Error).message });
    return data;
  }
}

/**
 * Mask sensitive headers (Authorization, API keys) from external call logs
 */
function maskHeaders(headers: any): any {
  if (!headers) return null;
  try {
    const copy = JSON.parse(JSON.stringify(headers));
    const sensitiveHeaderKeys = [
      'authorization', 'Authorization',
      'x-api-key', 'X-Api-Key',
      'api-key', 'Api-Key',
      'secret-key', 'Secret-Key',
      'cookie', 'Cookie',
      'set-cookie', 'Set-Cookie',
    ];

    for (const key of Object.keys(copy)) {
      if (sensitiveHeaderKeys.includes(key)) {
        const val = String(copy[key]);
        if (val.length > 8) {
          copy[key] = `${val.slice(0, 4)}***MASKED***`;
        } else {
          copy[key] = '***MASKED***';
        }
      }
    }

    return copy;
  } catch (error) {
    logger.warn('Failed to mask headers for logging, returning original headers', { error: (error as Error).message });
    return headers;
  }
}
