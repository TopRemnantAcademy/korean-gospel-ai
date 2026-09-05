import { Request, Response, NextFunction } from 'express';
import prisma from '../repositories/db';
import { generateUID, normalizePhone } from '../utils/uid';
import { encrypt, decrypt, sha256Hash, maskPhone, maskEmail } from '../utils/crypto';
import ssoService from '../services/sso.service';
import { socialIdentifySchema, ssoRequestSchema } from '@gospel-pay/shared';
import logger from '../utils/logger';

/**
 * socialIdentify Handler
 * 
 * Handles incoming social identification payload:
 * - If a user with the same provider/subject exists, return it.
 * - Account Linking Policy: If phone number is provided and its hash matches an existing user,
 *   we link/log in to that existing user, preventing duplicate profiles and preserving UID.
 * - Otherwise, create a new User and generate their deterministic UID (Priority 1: phone, Priority 2: provider).
 */
export async function socialIdentify(req: Request, res: Response, next: NextFunction) {
  try {
    const validated = socialIdentifySchema.parse(req.body);
    const { provider, providerSubject, email, phone } = validated;

    // 1. Check direct provider mapping
    let user = await prisma.user.findFirst({
      where: { provider, providerSubject, isDeleted: false },
    });

    if (user) {
      logger.info(`User identified directly by provider: ${provider}/${providerSubject}`, { uid: user.uid });
      return res.json({
        userId: user.id,
        uid: user.uid,
        emailMasked: maskEmail(decrypt(user.emailEncrypted)),
        phoneMasked: maskPhone(decrypt(user.phoneEncrypted)),
      });
    }

    // 2. Account Linking Policy: Check if phone number matches an existing user
    if (phone) {
      const phoneHashValue = sha256Hash(normalizePhone(phone))!;
      const existingUserByPhone = await prisma.user.findFirst({
        where: { phoneHash: phoneHashValue, isDeleted: false },
      });

      if (existingUserByPhone) {
        logger.info(`Account Linking: Linked new login ${provider}/${providerSubject} to existing user by phone`, { uid: existingUserByPhone.uid });
        
        // Update user to store last login timestamp
        await prisma.user.update({
          where: { id: existingUserByPhone.id },
          data: { lastLoginAt: new Date() },
        });

        return res.json({
          userId: existingUserByPhone.id,
          uid: existingUserByPhone.uid,
          emailMasked: maskEmail(decrypt(existingUserByPhone.emailEncrypted)),
          phoneMasked: maskPhone(phone),
        });
      }
    }

    // 3. New User Registration
    const timestamp = Date.now();
    const uid = generateUID({
      phone,
      createdAtTimestamp: timestamp,
      provider,
      providerSubject,
    });

    const emailEnc = email ? encrypt(email) : null;
    const emailHashVal = email ? sha256Hash(email) : null;
    const phoneEnc = phone ? encrypt(phone) : null;
    const phoneHashVal = phone ? sha256Hash(normalizePhone(phone)) : null;
    const phoneLast4 = phone ? normalizePhone(phone).slice(-4) : null;

    user = await prisma.user.create({
      data: {
        uid,
        provider,
        providerSubject,
        emailEncrypted: emailEnc,
        emailHash: emailHashVal,
        phoneEncrypted: phoneEnc,
        phoneHash: phoneHashVal,
        phoneLast4,
        registeredIp: req.ip || null,
        lastLoginAt: new Date(),
      },
    });

    logger.info(`Registered new user: provider=${provider}, uid=${uid.slice(0, 8)}...`);

    // Record consent policy for privacy auditing
    await prisma.consentRecord.create({
      data: {
        userId: user.id,
        consentType: 'TERMS_AND_PRIVACY_AGREEMENT',
        version: '1.0',
        agreed: true,
        disclosedItems: {
          uid: 'Hashed identifier for third-party billing',
          purpose: 'Credit Charge Handoff',
        },
        country: 'KR',
        transferTimeDesc: 'On-demand SSO navigation',
        transferMethod: 'User Browser HTTPS Post SSO redirect',
        recipientName: 'China Processing Server',
        recipientContact: 'china-support@worksite.example.com',
        purpose: 'Credit Charging and Syncing',
        retentionPeriod: 'Until user request deletion or service termination',
        refusalMethod: 'Unsubscribe or account withdrawal',
        refusalEffect: 'Unable to use cross-border credit syncing functions',
        ipAddress: req.ip || '127.0.0.1',
        userAgent: req.headers['user-agent'] || 'Unknown',
      },
    });

    return res.status(201).json({
      userId: user.id,
      uid: user.uid,
      emailMasked: email ? maskEmail(email) : undefined,
      phoneMasked: phone ? maskPhone(phone) : undefined,
    });
  } catch (error) {
    next(error);
  }
}

/**
 * issueSSOToken Handler
 * 
 * Verifies User, checks redirect allowlist, issues SSO signed JWT
 */
export async function issueSSOToken(req: Request, res: Response, next: NextFunction) {
  try {
    const validated = ssoRequestSchema.parse(req.body);
    const { uid, redirectUrl } = validated;

    const user = await prisma.user.findFirst({
      where: { uid, isDeleted: false },
    });

    if (!user) {
      return res.status(404).json({ error: 'User matching UID not found' });
    }

    const token = await ssoService.issueToken(uid, redirectUrl);

    return res.json({
      token,
      redirectUrl: `${redirectUrl}?token=${token}`,
    });
  } catch (error: any) {
    return res.status(400).json({ error: error.message });
  }
}

/**
 * introspectSSOToken Handler (used by external/Chinese server)
 */
export async function introspectSSOToken(req: Request, res: Response, next: NextFunction) {
  try {
    const { token } = req.body;
    if (!token) {
      return res.status(400).json({ error: 'SSO Token is required' });
    }

    const result = await ssoService.verifyToken(token);
    if (result.success) {
      return res.json({ active: true, uid: result.uid });
    } else {
      return res.status(400).json({ active: false, error: result.error });
    }
  } catch (error) {
    next(error);
  }
}
