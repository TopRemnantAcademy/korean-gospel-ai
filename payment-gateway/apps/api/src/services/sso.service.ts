import crypto from 'crypto';
import jwt from 'jsonwebtoken';
import { env } from '../config/env';
import redis from '../utils/redis';
import logger from '../utils/logger';

export interface SSOTokenClaims {
  iss: string;
  aud: string;
  sub: string;
  jti: string;
  iat: number;
  exp: number;
  nonce: string;
}

export class SSOService {
  private readonly secret = env.SSO_JWT_SECRET;
  private readonly redirectAllowlist = env.SSO_REDIRECT_ALLOWLIST;

  /**
   * Validates if a redirect URL matches the allowed list of origins/domains
   */
  public isValidRedirect(redirectUrl: string): boolean {
    try {
      const parsedUrl = new URL(redirectUrl);
      const origin = parsedUrl.origin;
      
      const allowed = this.redirectAllowlist.some((allowedOrigin) => {
        return allowedOrigin.trim().toLowerCase() === origin.toLowerCase();
      });

      if (!allowed) {
        logger.warn(`SSO Blocked: origin '${origin}' is not in allowlist. Allowed: ${this.redirectAllowlist.join(', ')}`);
      }
      return allowed;
    } catch {
      return false;
    }
  }

  /**
   * Issues a short-lived (60s) SSO JWT token and records the JTI in Redis
   */
  public async issueToken(uid: string, redirectUrl: string): Promise<string> {
    if (!this.isValidRedirect(redirectUrl)) {
      throw new Error('Redirect URL not in security allowlist');
    }

    const jti = crypto.randomUUID();
    const nonce = crypto.randomBytes(16).toString('hex');
    const iat = Math.floor(Date.now() / 1000);
    const exp = iat + 60; // 1-minute expiration

    const claims: SSOTokenClaims = {
      iss: 'gospel-pay-auth-korea',
      aud: 'china-worksite',
      sub: uid,
      jti,
      iat,
      exp,
      nonce,
    };

    const token = jwt.sign(claims, this.secret, { algorithm: 'HS256' });

    // Do NOT pre-create the JTI key in Redis here.
    // The verifyToken method will atomically SET the key with NX when consuming the token.
    // This prevents the race condition where issueToken creates the key as 'ACTIVE',
    // which would block verifyToken's NX SET from succeeding.

    logger.info(`Issued SSO Token: uid=${uid.slice(0, 8)}..., jti=${jti}`);
    return token;
  }

  /**
   * Introspects and verifies the SSO token (typically called by Chinese server or internal verification api)
   */
  public async verifyToken(token: string): Promise<{ success: boolean; uid?: string; error?: string }> {
    try {
      const decoded = jwt.verify(token, this.secret, { algorithms: ['HS256'] }) as SSOTokenClaims;
      
      // Prevent replay attack by checking Redis JTI atomically
      // Use SET with NX (only set if not exists) to make check-and-mark atomic
      const jtiKey = `sso:jti:${decoded.jti}`;
      const setResult = await redis.set(jtiKey, 'USED', 'EX', 120, 'NX');

      if (!setResult) {
        // Key already existed — either ACTIVE (already used) or expired
        const existingStatus = await redis.get(jtiKey);
        if (existingStatus === 'USED') {
          return { success: false, error: 'Token already used (replay attack detected)' };
        }
        return { success: false, error: 'Token has expired or was already consumed' };
      }

      logger.info(`SSO Token Verified and Consumed: sub(uid)=${decoded.sub.slice(0, 8)}..., jti=${decoded.jti}`);

      return {
        success: true,
        uid: decoded.sub,
      };
    } catch (err: any) {
      logger.error(`SSO Token verification failed: ${err.message}`);
      return {
        success: false,
        error: err.message,
      };
    }
  }
}

export default new SSOService();
