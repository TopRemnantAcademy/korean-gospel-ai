import app from './app';
import { env } from './config/env';
import prisma from './repositories/db';
import logger from './utils/logger';
import { PaymentMethod, AdminRole } from '@gospel-pay/shared';
import bcrypt from 'bcryptjs';

// Import workers to ensure they start listening to BullMQ queues
import './workers/workers';

const ADMIN_EMAIL = env.ADMIN_EMAIL;
const ADMIN_PASSWORD = env.ADMIN_PASSWORD;
const BCRYPT_ROUNDS = 12;

async function bootstrap() {
  try {
    logger.info('Bootstrapping GOSPEL PAY payment server...');

    // 1. Seed default payment methods configurations
    const countConfigs = await prisma.paymentMethodConfig.count();
    if (countConfigs === 0) {
      logger.info('Seeding default payment method configs...');
      const defaultMethods = [
        { method: PaymentMethod.CREDIT_CARD, display: '신용카드', refund: true, partial: true, cash: false },
        { method: PaymentMethod.KAKAO_PAY, display: '카카오페이 (간편결제)', refund: true, partial: true, cash: false },
        { method: PaymentMethod.NAVER_PAY, display: '네이버페이 (간편결제)', refund: true, partial: true, cash: false },
      ];

      for (let i = 0; i < defaultMethods.length; i++) {
        const m = defaultMethods[i];
        await prisma.paymentMethodConfig.create({
          data: {
            paymentMethod: m.method,
            enabled: true,
            pgProvider: 'TOSS_PAYMENTS',
            displayName: m.display,
            sortOrder: i,
            supportsRefund: m.refund,
            supportsPartialRefund: m.partial,
            supportsCashReceipt: m.cash,
            supportsVirtualAccountExpiry: m.method === PaymentMethod.VIRTUAL_ACCOUNT,
            supportsAutoRefund: true,
          },
        });
      }
      logger.info('Payment method configs successfully seeded.');
    }

    // 2. Seed default super admin user if not present (with bcrypt-hashed password)
    const countAdmins = await prisma.adminUser.count();
    if (countAdmins === 0) {
      logger.info('Seeding default administrator account with bcrypt-hashed password...');
      const hashedPassword = await bcrypt.hash(ADMIN_PASSWORD, BCRYPT_ROUNDS);
      await prisma.adminUser.create({
        data: {
          email: ADMIN_EMAIL,
          passwordHash: hashedPassword,
          role: AdminRole.SUPER_ADMIN,
          isActive: true,
        },
      });
      logger.info(`Auto-seeded ${ADMIN_EMAIL} as SUPER_ADMIN.`);
    }

    // 3. Seed data retention policies
    const countPolicies = await prisma.dataRetentionPolicy.count();
    if (countPolicies === 0) {
      logger.info('Seeding default data retention policies...');
      await prisma.dataRetentionPolicy.create({
        data: {
          dataCategory: 'PII_DELETED_USERS',
          retentionDays: 30, // Delete PII 30 days after user deletion
          disposalMethod: 'DELETE',
          isActive: true,
        },
      });
      await prisma.dataRetentionPolicy.create({
        data: {
          dataCategory: 'PAYMENT_RAW_PAYLOADS',
          retentionDays: 1825, // Keep payments LEDGER for 5 years, clean up raw JSON log data
          disposalMethod: 'MASK',
          isActive: true,
        },
      });
      logger.info('Data retention policies successfully seeded.');
    }

    // 4. Start HTTP Server listening
    app.listen(env.PORT, () => {
      logger.info(`🚀 GOSPEL PAY Server listening on port ${env.PORT} [ENV: ${env.NODE_ENV}]`);
    });
  } catch (error) {
    logger.error(`Bootstrap failed: ${(error as Error).message}`);
    process.exit(1);
  }
}

bootstrap();
