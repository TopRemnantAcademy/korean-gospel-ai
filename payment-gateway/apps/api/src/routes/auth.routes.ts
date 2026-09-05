import { Router } from 'express';
import { socialIdentify, issueSSOToken, introspectSSOToken } from '../controllers/auth.controller';
import { authLimiter } from '../middlewares/rateLimiter';

const router = Router();

router.post('/social/identify', authLimiter, socialIdentify);
router.post('/auth/sso', authLimiter, issueSSOToken);
router.post('/sso-token', authLimiter, issueSSOToken);
router.post('/sso/introspect', authLimiter, introspectSSOToken);

export default router;
