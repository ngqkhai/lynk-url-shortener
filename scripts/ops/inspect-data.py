#!/usr/bin/env python3
"""Read aggregate data fingerprints through each owning service's connection."""

import datetime
import json
import subprocess


SERVICES = {
    "auth-service": ("lynk_auth", "lynk_auth", ["users", "refresh_sessions", "refresh_tokens", "access_tokens"]),
    "url-service": ("lynk_urls", "lynk_url", ["urls", "url_outbox"]),
    "redirect-service": ("lynk_redirects", "lynk_redirect", ["redirect_urls"]),
}

PROGRAM = r"""
const postgres = require('postgres');
const sql = postgres(process.env.DATABASE_URL, {max: 1, connect_timeout: 10});
sql.unsafe(process.argv[1]).then(async rows => {
  process.stdout.write(JSON.stringify(rows[0]));
  await sql.end({timeout: 3});
}).catch(async error => {
  process.stderr.write(error.code || 'DATABASE_INSPECTION_FAILED');
  await sql.end({timeout: 3});
  process.exitCode = 1;
});
"""


def main():
    result = {}
    for service, (database, role, tables) in SERVICES.items():
        parts = []
        for table in tables:
            # Table names come only from the fixed allowlist above. Row values
            # stay in PostgreSQL; MD5 is a consistency checksum, not encryption.
            parts.append(
                "'" + table + "', (select json_build_object('rows', count(*), "
                "'checksum', md5(coalesce(string_agg(md5(row_to_json(t)::text), '' "
                "order by md5(row_to_json(t)::text)), ''))) from public.\""
                + table + "\" t)"
            )
        query = (
            "select current_database() as database, current_user as role, "
            "current_setting('server_version') as server_version, json_build_object("
            + ", ".join(parts) + ") as tables"
        )
        raw = subprocess.check_output(
            ["kubectl", "-n", "lynk-aws", "exec", "deployment/" + service,
             "--", "node", "-e", PROGRAM, query], text=True, timeout=45,
        )
        data = json.loads(raw)
        if data["database"] != database or data["role"] != role:
            raise RuntimeError("Unexpected database ownership for " + service)
        result[service] = data
    print(json.dumps({
        "observed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "services": result,
        "scope": "Seven allowlisted application tables; counts and non-security aggregate MD5 only",
    }))


if __name__ == "__main__":
    main()
