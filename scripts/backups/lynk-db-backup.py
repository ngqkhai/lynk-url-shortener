#!/usr/bin/env python3
"""Back up one Lynk-owned Neon database and prune only after a verified success."""
import argparse
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import subprocess
import sys
import tempfile
import time
from urllib.parse import unquote, urlsplit
import uuid

REGION = "ap-southeast-1"
NAMESPACE = "lynk-aws"
KEEP_SUCCESSFUL = 7
SERVICES = {
    "url": {"secret": "url-service-db", "database": "lynk_urls", "role": "lynk_url"},
    "redirect": {"secret": "redirect-service-db", "database": "lynk_redirects", "role": "lynk_redirect"},
    "auth": {"secret": "auth-service-db", "database": "lynk_auth", "role": "lynk_auth"},
}


class BackupFailure(RuntimeError):
    """A failure stage safe to report without exposing credentials or SQL output."""

    def __init__(self, stage):
        super().__init__(stage)
        self.stage = stage


def safe_command_failure(result):
    """Map subprocess diagnostics to a small, non-secret category vocabulary."""
    diagnostic = result.stderr
    if isinstance(diagnostic, bytes):
        diagnostic = diagnostic.decode(errors="replace")
    diagnostic = diagnostic.lower()
    for pattern, category in (
        ("permission denied", "database_permission_denied"),
        ("invalid snapshot", "snapshot_rejected"),
        ("snapshot", "snapshot_argument_or_visibility"),
        ("could not connect", "database_connection_failed"),
        ("timed out", "database_operation_timed_out"),
        ("does not exist", "database_object_missing"),
    ):
        if pattern in diagnostic:
            return category
    return "external_command_failed"


def database_environment(secret_json, service):
    expected = SERVICES[service]
    encoded = secret_json.get("data", {}).get("DATABASE_URL")
    if not encoded:
        raise ValueError("Service database Secret has no DATABASE_URL")
    raw = base64.b64decode(encoded, validate=True).decode()
    parsed = urlsplit(raw)
    database = unquote(parsed.path.lstrip("/"))
    role = unquote(parsed.username or "")
    host = parsed.hostname or ""
    if parsed.scheme not in ("postgres", "postgresql"):
        raise ValueError("Service database URL has an unsupported scheme")
    if database != expected["database"] or role != expected["role"]:
        raise ValueError("Service database URL violates the ownership map")
    if not host.endswith(".aws.neon.tech") or "-pooler." in host:
        raise ValueError("Database backup requires a direct Neon endpoint")
    if parsed.password is None:
        raise ValueError("Service database URL has no credential")
    port = parsed.port or 5432
    return {
        "PGHOST": host,
        "PGPORT": str(port),
        "PGDATABASE": database,
        "PGUSER": role,
        "PGPASSWORD": unquote(parsed.password),
        "PGSSLMODE": "verify-full",
        "PGSSLROOTCERT": "/etc/ssl/certs/ca-certificates.crt",
        "PGCONNECT_TIMEOUT": "15",
        "PGAPPNAME": "lynk-db-backup-" + service,
    }


def read_service_database_url(service, kubectl="/usr/local/bin/kubectl", runner=subprocess.run):
    result = runner(
        [kubectl, "-n", NAMESPACE, "get", "secret", SERVICES[service]["secret"], "-o", "json"],
        capture_output=True,
    )
    if result.returncode:
        raise RuntimeError("Could not read the service-owned database Secret")
    return json.loads(result.stdout)


@contextmanager
def exported_snapshot(environment, psql="/usr/bin/psql", timeout=90):
    process = subprocess.Popen(
        [psql, "-X", "-qAt", "-F", "\t", "-w"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, env={**os.environ, **environment}, bufsize=1,
    )
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)

    def read_line(deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not selector.select(remaining):
            process.kill()
            raise TimeoutError("Database snapshot metadata query timed out")
        line = process.stdout.readline()
        if not line:
            raise RuntimeError("Database snapshot metadata query failed")
        return line.rstrip("\r\n")

    try:
        process.stdin.write("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\nSELECT pg_export_snapshot();\n")
        process.stdin.flush()
        deadline = time.monotonic() + timeout
        snapshot = read_line(deadline)
        if not re.fullmatch(r"[0-9A-Fa-f-]+", snapshot):
            raise RuntimeError("PostgreSQL returned an invalid exported snapshot identifier")

        process.stdin.write(
            "SELECT format('SELECT %L, count(*) FROM %I.%I;', tablename, schemaname, tablename) "
            "FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename \\gexec\n"
            "SELECT '__CP11_ROW_COUNTS_END__';\n"
        )
        process.stdin.flush()
        row_counts = {}
        while True:
            line = read_line(deadline)
            if line == "__CP11_ROW_COUNTS_END__":
                break
            name, count = line.split("\t", 1)
            row_counts[name] = int(count)

        process.stdin.write(
            "SELECT contype::text, count(*) FROM pg_constraint "
            "WHERE connamespace = 'public'::regnamespace GROUP BY contype ORDER BY contype;\n"
            "SELECT '__CP11_CONSTRAINTS_END__';\n"
        )
        process.stdin.flush()
        constraints = {}
        while True:
            line = read_line(deadline)
            if line == "__CP11_CONSTRAINTS_END__":
                break
            name, count = line.split("\t", 1)
            constraints[name] = int(count)
        yield snapshot, row_counts, constraints
        process.stdin.write("COMMIT;\n\\q\n")
        process.stdin.flush()
        if process.wait(timeout=timeout) != 0:
            raise RuntimeError("Database snapshot metadata transaction failed")
    finally:
        selector.close()
        if process.poll() is None:
            process.kill()
            process.wait()


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    raw = digest.digest()
    return digest.hexdigest(), base64.b64encode(raw).decode()


def run_checked(command, env=None, runner=subprocess.run):
    result = runner(command, capture_output=True, env=env)
    if result.returncode:
        raise BackupFailure(safe_command_failure(result))
    return result


def verify_upload(bucket, key, path, runner=subprocess.run):
    digest_hex, digest_b64 = sha256_file(path)
    run_checked(
        ["/usr/local/bin/aws", "--region", REGION, "s3api", "put-object", "--bucket", bucket,
         "--key", key, "--body", str(path), "--server-side-encryption", "AES256",
         "--checksum-algorithm", "SHA256", "--checksum-sha256", digest_b64],
        runner=runner,
    )
    head = run_checked(
        ["/usr/local/bin/aws", "--region", REGION, "s3api", "head-object", "--bucket", bucket,
         "--key", key, "--checksum-mode", "ENABLED"], runner=runner,
    )
    metadata = json.loads(head.stdout)
    if metadata.get("ServerSideEncryption") != "AES256":
        raise RuntimeError("S3 backup object encryption is not SSE-S3")
    if metadata.get("ChecksumSHA256") != digest_b64 or metadata.get("ContentLength") != path.stat().st_size:
        raise RuntimeError("S3 backup object checksum or size does not match the local archive")
    return digest_hex


def successful_manifest_keys(objects, prefix):
    return sorted(
        [item["Key"] for item in objects if item.get("Key", "").startswith(prefix)
         and item["Key"].endswith(".manifest.json")],
        reverse=True,
    )


def prune_after_success(bucket, prefix, runner=subprocess.run, keep=KEEP_SUCCESSFUL):
    listed = run_checked(
        ["/usr/local/bin/aws", "--region", REGION, "s3api", "list-objects-v2", "--bucket", bucket,
         "--prefix", prefix], runner=runner,
    )
    objects = json.loads(listed.stdout).get("Contents", [])
    manifests = successful_manifest_keys(objects, prefix)
    for manifest in manifests[keep:]:
        archive = manifest.removesuffix(".manifest.json") + ".dump"
        # Delete the success marker first; a leftover archive is an inert orphan, not a false backup.
        run_checked(["/usr/local/bin/aws", "--region", REGION, "s3api", "delete-object",
                     "--bucket", bucket, "--key", manifest], runner=runner)
        run_checked(["/usr/local/bin/aws", "--region", REGION, "s3api", "delete-object",
                     "--bucket", bucket, "--key", archive], runner=runner)
    return min(len(manifests), keep)


def backup_service(service, bucket, kubectl="/usr/local/bin/kubectl", pg_dump="/usr/bin/pg_dump",
                   pg_restore="/usr/bin/pg_restore", psql="/usr/bin/psql", runner=subprocess.run):
    if service not in SERVICES:
        raise ValueError("Unknown database service")
    try:
        source = read_service_database_url(service, kubectl, runner)
        environment = database_environment(source, service)
    except Exception as error:
        raise BackupFailure("service_secret_or_ownership_validation") from error
    database = SERVICES[service]["database"]
    prefix = f"db-backups/{database}/"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = f"{prefix}{stamp}-{uuid.uuid4().hex}"
    with tempfile.TemporaryDirectory(prefix="lynk-db-backup-") as directory:
        root = Path(directory)
        archive = root / f"{database}.dump"
        archive.touch(mode=0o600)
        started = datetime.now(timezone.utc)
        try:
            with exported_snapshot(environment, psql) as (snapshot, row_counts, constraints):
                version = run_checked([pg_dump, "--version"], runner=runner).stdout.decode().strip()
                if " 18." not in version:
                    raise BackupFailure("postgres_client_version_mismatch")
                run_checked(
                    [pg_dump, "--no-password", "--format=custom", "--no-owner", "--no-acl",
                     "--snapshot", snapshot, "--file", str(archive)], env={**os.environ, **environment}, runner=runner,
                )
        except BackupFailure:
            raise
        except Exception as error:
            raise BackupFailure("read_only_snapshot_or_logical_dump") from error
        if not archive.is_file() or archive.stat().st_size == 0:
            raise RuntimeError("pg_dump produced an empty archive")
        listing = run_checked([pg_restore, "--list", str(archive)], runner=runner).stdout
        if not listing.strip():
            raise RuntimeError("pg_restore did not recognize the archive contents")
        dump_key = stem + ".dump"
        try:
            dump_sha = verify_upload(bucket, dump_key, archive, runner)
        except Exception as error:
            raise BackupFailure("archive_upload_or_integrity_check") from error
        finished = datetime.now(timezone.utc)
        manifest = {
            "status": "success", "service": service, "database": database,
            "role": SERVICES[service]["role"], "postgres_client": version,
            "snapshot_exported": True, "started_at": started.isoformat(),
            "completed_at": finished.isoformat(), "archive_key": dump_key,
            "archive_bytes": archive.stat().st_size, "archive_sha256": dump_sha,
            "row_counts": row_counts, "constraint_counts_by_type": constraints,
        }
        manifest_path = root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n")
        manifest_path.chmod(0o600)
        manifest_key = stem + ".manifest.json"
        try:
            verify_upload(bucket, manifest_key, manifest_path, runner)
        except Exception as error:
            raise BackupFailure("success_manifest_upload_or_integrity_check") from error
        try:
            retained = prune_after_success(bucket, prefix, runner)
        except Exception as error:
            raise BackupFailure("post_success_retention") from error
        return {"service": service, "database": database, "archive_bytes": archive.stat().st_size,
                "archive_sha256": dump_sha, "manifest_key": manifest_key, "successful_backups_retained": retained}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service", choices=tuple(SERVICES))
    parser.add_argument("--bucket", required=True)
    args = parser.parse_args()
    try:
        result = backup_service(args.service, args.bucket)
        print("Backup complete: " + json.dumps(result, sort_keys=True))
        return 0
    except Exception as error:
        # Exception strings from subprocesses and clients can include connection details.
        stage = error.stage if isinstance(error, BackupFailure) else type(error).__name__
        print(f"Backup failed for service {args.service} at {stage}; previous backups retained", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
