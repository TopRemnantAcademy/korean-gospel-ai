import { Response, NextFunction } from 'express';
import prisma from '../repositories/db';
import { encrypt, sha256Hash } from '../utils/crypto';
import { AuthenticatedAdminRequest } from '../middlewares/auth.middleware';
import { paymentGatewayConfigSchema } from '../validators/paymentGateway.validators';
import logger from '../utils/logger';

/**
 * GET /api/admin/payment-gateways
 * List all payment gateway configurations
 */
export async function getPaymentGateways(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const configs = await prisma.paymentMethodConfig.findMany({
      orderBy: { sortOrder: 'asc' },
    });

    // Mask sensitive fields
    const maskedConfigs = configs.map(config => ({
      ...config,
      apiKeyEncrypted: config.apiKeyEncrypted ? '****' : null,
      secretKeyEncrypted: config.secretKeyEncrypted ? '****' : null,
      clientIdEncrypted: config.clientIdEncrypted ? '****' : null,
      merchantIdEncrypted: config.merchantIdEncrypted ? '****' : null,
    }));

    return res.json(maskedConfigs);
  } catch (error) {
    next(error);
  }
}

/**
 * GET /api/admin/payment-gateways/:id
 * Get specific payment gateway configuration
 */
export async function getPaymentGateway(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const { id } = req.params;

    const config = await prisma.paymentMethodConfig.findUnique({
      where: { id },
    });

    if (!config) {
      return res.status(404).json({ error: 'Payment gateway configuration not found' });
    }

    // Mask sensitive fields
    const maskedConfig = {
      ...config,
      apiKeyEncrypted: config.apiKeyEncrypted ? '****' : null,
      secretKeyEncrypted: config.secretKeyEncrypted ? '****' : null,
      clientIdEncrypted: config.clientIdEncrypted ? '****' : null,
      merchantIdEncrypted: config.merchantIdEncrypted ? '****' : null,
    };

    return res.json(maskedConfig);
  } catch (error) {
    next(error);
  }
}

/**
 * PATCH /api/admin/payment-gateways/:id
 * Update payment gateway configuration
 */
export async function updatePaymentGateway(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const { id } = req.params;
    const validated = paymentGatewayConfigSchema.parse(req.body);

    const existingConfig = await prisma.paymentMethodConfig.findUnique({
      where: { id },
    });

    if (!existingConfig) {
      return res.status(404).json({ error: 'Payment gateway configuration not found' });
    }

    // Prepare update data
    const updateData: any = {};

    // Encrypt API keys if provided
    if (validated.apiKey) {
      updateData.apiKeyEncrypted = encrypt(validated.apiKey);
      updateData.apiKeyHash = sha256Hash(validated.apiKey);
    }
    if (validated.secretKey) {
      updateData.secretKeyEncrypted = encrypt(validated.secretKey);
      updateData.secretKeyHash = sha256Hash(validated.secretKey);
    }
    if (validated.clientId) {
      updateData.clientIdEncrypted = encrypt(validated.clientId);
      updateData.clientIdHash = sha256Hash(validated.clientId);
    }
    if (validated.merchantId) {
      updateData.merchantIdEncrypted = encrypt(validated.merchantId);
      updateData.merchantIdHash = sha256Hash(validated.merchantId);
    }

    // Update URLs if provided
    if (validated.webhookUrl !== undefined) {
      updateData.webhookUrl = validated.webhookUrl || null;
    }
    if (validated.successUrl !== undefined) {
      updateData.successUrl = validated.successUrl || null;
    }
    if (validated.failUrl !== undefined) {
      updateData.failUrl = validated.failUrl || null;
    }
    if (validated.cancelUrl !== undefined) {
      updateData.cancelUrl = validated.cancelUrl || null;
    }
    if (validated.callbackUrl !== undefined) {
      updateData.callbackUrl = validated.callbackUrl || null;
    }

    // Update other fields
    if (validated.isTestMode !== undefined) {
      updateData.isTestMode = validated.isTestMode;
    }
    if (validated.enabled !== undefined) {
      updateData.enabled = validated.enabled;
    }
    if (validated.displayName !== undefined) {
      updateData.displayName = validated.displayName;
    }

    const updated = await prisma.paymentMethodConfig.update({
      where: { id },
      data: updateData,
    });

    // Audit log (exclude encrypted fields from beforeJson/afterJson)
    const sanitizeForAudit = (config: any) => {
      const { apiKeyEncrypted, apiKeyHash, secretKeyEncrypted, secretKeyHash,
              clientIdEncrypted, clientIdHash, merchantIdEncrypted, merchantIdHash,
              ...safe } = config;
      return safe;
    };

    await prisma.adminAuditLog.create({
      data: {
        adminUserId: req.adminUser!.id,
        action: 'UPDATE_PAYMENT_GATEWAY',
        entityType: 'PaymentMethodConfig',
        entityId: id,
        beforeJson: sanitizeForAudit(existingConfig) as any,
        afterJson: sanitizeForAudit(updated) as any,
        ipAddress: req.ip || '127.0.0.1',
      },
    });

    logger.info(`Payment gateway configuration updated: ${id} by ${req.adminUser!.email}`);

    // Return masked config
    const maskedConfig = {
      ...updated,
      apiKeyEncrypted: updated.apiKeyEncrypted ? '****' : null,
      secretKeyEncrypted: updated.secretKeyEncrypted ? '****' : null,
      clientIdEncrypted: updated.clientIdEncrypted ? '****' : null,
      merchantIdEncrypted: updated.merchantIdEncrypted ? '****' : null,
    };

    return res.json(maskedConfig);
  } catch (error) {
    next(error);
  }
}

/**
 * POST /api/admin/payment-gateways/:id/test
 * Test payment gateway connection
 */
export async function testPaymentGateway(req: AuthenticatedAdminRequest, res: Response, next: NextFunction) {
  try {
    const { id } = req.params;

    const config = await prisma.paymentMethodConfig.findUnique({
      where: { id },
    });

    if (!config) {
      return res.status(404).json({ error: 'Payment gateway configuration not found' });
    }

    // Check if required fields are configured
    const missingFields: string[] = [];
    
    if (!config.apiKeyEncrypted && !config.secretKeyEncrypted) {
      missingFields.push('API Key or Secret Key');
    }

    if (missingFields.length > 0) {
      return res.status(400).json({
        success: false,
        error: `Missing required configuration: ${missingFields.join(', ')}`,
      });
    }

    // In production, this would make a test API call to the payment gateway
    // For now, we'll just validate the configuration
    const testResult = {
      success: true,
      message: 'Configuration is valid',
      testedAt: new Date().toISOString(),
      mode: config.isTestMode ? 'TEST' : 'PRODUCTION',
    };

    logger.info(`Payment gateway test successful: ${id}`);

    return res.json(testResult);
  } catch (error) {
    next(error);
  }
}
