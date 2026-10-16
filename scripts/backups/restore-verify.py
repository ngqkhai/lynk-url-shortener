#!/usr/bin/env python3
"""Restore one verified Lynk custom archive into an isolated local PostgreSQL 18 cluster."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time


def run(command, **kwargs):
    result = subprocess.run(command, capture_output=True, text=True, **kwargs)
    if result.returncode:
        raise RuntimeError(f"Local PostgreSQL restore command failed ({Path(command[0]).name}, exit {result.returncode}): {result.stderr.strip()}")
    return result.stdout


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def verify_restore(archive, manifest_path, bindir=None, share=None):
    started = time.monotonic()
    archive, manifest_path = Path(archive), Path(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("status") != "success" or digest(archive) != manifest.get("archive_sha256"):
        raise ValueError("Manifest status or archive SHA-256 verification failed")
    if not re.fullmatch(r"lynk_[a-z]+", manifest.get("database", "")):
        raise ValueError("Unexpected database name in backup manifest")
    if manifest.get("postgres_client", "").find("18.") < 0:
        raise ValueError("Backup was not created with PostgreSQL 18 client")
    bindir = Path(bindir or run(["pg_config", "--bindir"]).strip())
    initdb, pg_ctl = bindir / "initdb", bindir / "pg_ctl"
    pg_restore, psql, createdb = bindir / "pg_restore", bindir / "psql", bindir / "createdb"
    with tempfile.TemporaryDirectory(prefix="lynk-db-restore-") as temporary:
        root = Path(temporary)
        data = root / "data"
        init_command = [str(initdb), "--no-sync", "--auth-local=trust", "--auth-host=reject", "-U", "restore_verify", "-D", str(data)]
        if share:
            init_command.extend(["-L", str(share)])
        run(init_command)
        port = 5432  # No TCP listener; each restore uses a private Unix socket directory.
        socket_dir = root / "socket"
        socket_dir.mkdir(mode=0o700)
        log = root / "postgres.log"
        try:
            run([str(pg_ctl), "-D", str(data), "-l", str(log), "-o", f"-p {port} -c listen_addresses= -c unix_socket_directories={socket_dir}", "-w", "start"])
            env = {key: os.environ[key] for key in ("PATH", "LD_LIBRARY_PATH", "LANG", "LC_ALL") if key in os.environ}
            env.update({"PGHOST": str(socket_dir), "PGPORT": str(port), "PGUSER": "restore_verify", "PGDATABASE": "postgres"})
            run([str(createdb), "--no-password", "--template=template0", "restore_check"], env=env)
            env["PGDATABASE"] = "restore_check"
            run([str(pg_restore), "--exit-on-error", "--no-owner", "--no-acl", "-d", "restore_check", str(archive)], env=env)
            table_query = (
                "SELECT format('SELECT %L, count(*) FROM %I.%I;', tablename, schemaname, tablename) "
                "FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename \\gexec\n"
            )
            row_output = run([str(psql), "-X", "-qAt", "-F", "\t", "-v", "ON_ERROR_STOP=1"], input=table_query, env=env)
            rows = {name: int(count) for name, count in (line.split("\t", 1) for line in row_output.splitlines())}
            constraints_output = run([str(psql), "-X", "-qAt", "-F", "\t", "-v", "ON_ERROR_STOP=1"], input=(
                "SELECT contype::text, count(*) FROM pg_constraint "
                "WHERE connamespace = 'public'::regnamespace GROUP BY contype ORDER BY contype;\n"
            ), env=env)
            constraints = {name: int(count) for name, count in (line.split("\t", 1) for line in constraints_output.splitlines())}
            if rows != manifest.get("row_counts"):
                raise ValueError("Restored public table row counts do not match the backup snapshot")
            if constraints != manifest.get("constraint_counts_by_type"):
                raise ValueError(f"Restored public constraint counts do not match the backup snapshot: {constraints}")
            return {"database": manifest["database"], "row_counts": rows, "constraint_counts_by_type": constraints,
                    "archive_sha256": manifest["archive_sha256"], "restore_seconds": round(time.monotonic() - started, 3),
                    "verified_at": datetime.now(timezone.utc).isoformat(), "restore_target": "isolated local PostgreSQL 18"}
        finally:
            subprocess.run([str(pg_ctl), "-D", str(data), "-m", "immediate", "-w", "stop"], capture_output=True, text=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive")
    parser.add_argument("manifest")
    parser.add_argument("--bindir")
    parser.add_argument("--share")
    args = parser.parse_args()
    print(json.dumps(verify_restore(args.archive, args.manifest, args.bindir, args.share), sort_keys=True))


if __name__ == "__main__":
    main()
