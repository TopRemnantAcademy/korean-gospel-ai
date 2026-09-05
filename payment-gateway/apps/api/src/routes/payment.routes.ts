import { Router } from 'express';
import { 
  getPaymentMethods, 
  getProducts, 
  preparePayment, 
  pgCallback, 
  getPaymentStatus,
  handlePgWebhook,
  handleRemoteWebhook
} from '../controllers/payment.controller';

import { publicApiLimiter, paymentLimiter } from '../middlewares/rateLimiter';

const router = Router();

router.get('/payment-methods', publicApiLimiter, getPaymentMethods);
router.get('/products', publicApiLimiter, getProducts);
router.post('/payments/prepare', paymentLimiter, preparePayment);
router.post('/payments/callback', paymentLimiter, pgCallback);
router.post('/payments/webhook', paymentLimiter, handlePgWebhook);
router.post('/payments/remote-webhook', publicApiLimiter, handleRemoteWebhook);
router.get('/payments/:paymentUuid/status', publicApiLimiter, getPaymentStatus);

export default router;
