import { URL } from 'node:url';
import { execFileSync } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import postgres from 'postgres';
const project = 'restless-water-85518233';
const secretFile = process.env.LYNK_NEON_SECRETS_FILE ?? '/tmp/lynk-neon-databases.json';
const adminUri = execFileSync(
  'neon',
  [
    'connection-string',
    'production',
    '--project-id',
    project,
    '--role-name',
    'neondb_owner',
    '--database-name',
    'neondb',
  ],
  { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] },
).trim();
const sql = postgres(adminUri, { max: 1, connect_timeout: 15 });
const entries = existsSync(secretFile) ? JSON.parse(readFileSync(secretFile, 'utf8')) : {};
try {
  for (const [service, name, role] of [
    ['url', 'lynk_urls', 'lynk_url'],
    ['redirect', 'lynk_redirects', 'lynk_redirect'],
    ['auth', 'lynk_auth', 'lynk_auth'],
  ]) {
    const password = entries[service]?.password ?? randomBytes(32).toString('hex');
    const uri = new URL(adminUri);
    uri.username = role;
    uri.password = password;
    uri.pathname = `/${name}`;
    const saved = entries[service];
    const [existingRole] = await sql`select 1 from pg_roles where rolname=${role}`;
    if (existingRole && !saved && process.env.LYNK_RECOVER_FRESH_ROLE !== role)
      throw new Error(`Existing role ${role}: restore credentials before continuing`);
    entries[service] = { database: name, role, password, uri: uri.toString() };
    writeFileSync(secretFile, JSON.stringify(entries), { mode: 0o600 });
    if (!existingRole)
      await sql.unsafe(
        `create role "${role}" login password '${password}' nosuperuser nocreatedb nocreaterole noinherit`,
      );
    else if (!saved) {
      if (process.env.LYNK_RECOVER_FRESH_ROLE !== role)
        throw new Error(`Existing role ${role}: restore credentials before continuing`);
      await sql.unsafe(`alter role "${role}" password '${password}'`);
    }
    await sql.unsafe(`grant "${role}" to neondb_owner with set true`);
    const [existingDb] =
      await sql`select pg_get_userbyid(datdba) as owner from pg_database where datname=${name}`;
    if (existingDb && existingDb.owner !== role)
      throw new Error(`Database ${name} has an unexpected owner; refusing to change grants`);
    if (!existingDb) await sql.unsafe(`create database "${name}" owner "${role}"`);
    await sql.unsafe(`set role "${role}"`);
    await sql.unsafe(`revoke connect on database "${name}" from public`);
    await sql.unsafe(`grant connect on database "${name}" to "${role}", neondb_owner`);
    await sql.unsafe(`reset role`);
    process.stdout.write(`Ready: ${name}, isolated role ${role}\n`);
  }
} catch (error) {
  process.stderr.write(`Neon provisioning failed: ${error.code ?? error.name}: ${error.message}\n`);
  process.exitCode = 1;
} finally {
  await sql.end({ timeout: 5 });
}
