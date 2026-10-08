import { createPublicKey } from 'node:crypto';
import { importSPKI, jwtVerify, SignJWT } from 'jose';
import { z } from 'zod';

export const JWT_ISSUER = 'lynk-auth';
export const JWT_AUDIENCE = 'lynk-api';
export const opaqueAccessSchema = z.string().regex(/^at_[A-Za-z0-9_-]{43}$/);
export const opaqueRefreshSchema = z.string().regex(/^rt_[A-Za-z0-9_-]{43}$/);
export interface Principal {
  userId: string;
  sessionId: string;
  accessId: string;
}
const claimsSchema = z.object({
  sub: z.string().uuid(),
  sid: z.string().uuid(),
  atid: z.string().uuid(),
  iat: z.number().int(),
  exp: z.number().int(),
  jti: z.string().uuid(),
});

export type PrincipalVerifier = (authorization: string | undefined) => Promise<Principal>;
export function createPrincipalVerifier(publicKeyPem: string): PrincipalVerifier {
  const parsedKey = createPublicKey(publicKeyPem);
  if (
    parsedKey.asymmetricKeyType !== 'rsa' ||
    (parsedKey.asymmetricKeyDetails?.modulusLength ?? 0) < 2048
  )
    throw new Error('Expected RSA public key with at least 2048 bits');
  const key = importSPKI(publicKeyPem, 'RS256');
  return async (authorization) => {
    const match = /^Bearer ([^\s]+)$/i.exec(authorization ?? '');
    if (!match) throw new Error('Missing bearer token');
    const { payload, protectedHeader } = await jwtVerify(match[1], await key, {
      algorithms: ['RS256'],
      issuer: JWT_ISSUER,
      audience: JWT_AUDIENCE,
      requiredClaims: ['exp', 'iat', 'sub', 'jti', 'sid', 'atid'],
    });
    if (!protectedHeader.kid) throw new Error('Missing signing key identifier');
    const claims = claimsSchema.parse(payload);
    if (
      claims.exp - claims.iat > 60 ||
      claims.exp <= claims.iat ||
      claims.iat > Math.floor(Date.now() / 1000)
    )
      throw new Error('Invalid internal token lifetime');
    return { userId: claims.sub, sessionId: claims.sid, accessId: claims.atid };
  };
}

export async function signInternalToken(
  key: CryptoKey,
  keyId: string,
  principal: Principal,
  expiresAt: Date,
  now: Date = new Date(),
  jti: string = crypto.randomUUID(),
): Promise<string> {
  return new SignJWT({ sid: principal.sessionId, atid: principal.accessId })
    .setProtectedHeader({ alg: 'RS256', kid: keyId, typ: 'JWT' })
    .setSubject(principal.userId)
    .setIssuer(JWT_ISSUER)
    .setAudience(JWT_AUDIENCE)
    .setIssuedAt(Math.floor(now.getTime() / 1000))
    .setExpirationTime(Math.floor(expiresAt.getTime() / 1000))
    .setJti(jti)
    .sign(key);
}
