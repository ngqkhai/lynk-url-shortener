import { describe, expect, it } from 'vitest';
import { generateKeyPair, exportSPKI, SignJWT } from 'jose';
import { randomUUID } from 'node:crypto';
import { createPrincipalVerifier, signInternalToken } from '../src/auth.js';

describe('internal JWT trust boundary', () => {
  it('verifies internal claims and rejects opaque, expired, wrong audience and another signing key', async () => {
    const { privateKey, publicKey } = await generateKeyPair('RS256');
    const verify = createPrincipalVerifier(await exportSPKI(publicKey));
    const principal = { userId: randomUUID(), sessionId: randomUUID(), accessId: randomUUID() };
    const token = await signInternalToken(
      privateKey,
      'local-v1',
      principal,
      new Date(Date.now() + 60000),
    );
    expect(await verify(`Bearer ${token}`)).toEqual(principal);
    await expect(verify(`Bearer at_${'a'.repeat(43)}`)).rejects.toThrow();
    const expired = await signInternalToken(
      privateKey,
      'local-v1',
      principal,
      new Date(Date.now() - 1000),
    );
    await expect(verify(`Bearer ${expired}`)).rejects.toThrow();
    const wrongAudience = await new SignJWT({ sid: principal.sessionId, atid: principal.accessId })
      .setProtectedHeader({ alg: 'RS256', kid: 'local-v1' })
      .setSubject(principal.userId)
      .setIssuer('lynk-auth')
      .setAudience('other')
      .setIssuedAt()
      .setExpirationTime('60s')
      .setJti(randomUUID())
      .sign(privateKey);
    await expect(verify(`Bearer ${wrongAudience}`)).rejects.toThrow();
    for (const [issuer, subject] of [
      ['other-issuer', principal.userId],
      ['lynk-auth', 'invalid-uuid'],
    ]) {
      const invalid = await new SignJWT({ sid: principal.sessionId, atid: principal.accessId })
        .setProtectedHeader({ alg: 'RS256', kid: 'local-v1' })
        .setSubject(subject)
        .setIssuer(issuer)
        .setAudience('lynk-api')
        .setIssuedAt()
        .setExpirationTime('60s')
        .setJti(randomUUID())
        .sign(privateKey);
      await expect(verify(`Bearer ${invalid}`)).rejects.toThrow();
    }
    const wrongAlgorithm = await new SignJWT({})
      .setProtectedHeader({ alg: 'HS256', kid: 'local-v1' })
      .sign(new TextEncoder().encode('local-test-hmac-secret-at-least-32-bytes'));
    await expect(verify(`Bearer ${wrongAlgorithm}`)).rejects.toThrow();
    const tooLong = await signInternalToken(
      privateKey,
      'local-v1',
      principal,
      new Date(Date.now() + 90000),
    );
    await expect(verify(`Bearer ${tooLong}`)).rejects.toThrow();
    const parts = token.split('.');
    parts[2] = (parts[2][0] === 'A' ? 'B' : 'A') + parts[2].slice(1);
    await expect(verify(`Bearer ${parts.join('.')}`)).rejects.toThrow();
    const other = await generateKeyPair('RS256');
    const forged = await signInternalToken(
      other.privateKey,
      'local-v1',
      principal,
      new Date(Date.now() + 60000),
    );
    await expect(verify(`Bearer ${forged}`)).rejects.toThrow();
  });
});
