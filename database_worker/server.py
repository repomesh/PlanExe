"""Minimal HTTP server that streams pg_dump output as a compressed download."""
import os
import shutil
import subprocess
import logging
from datetime import datetime, UTC
from http.server import HTTPServer, BaseHTTPRequestHandler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PGHOST = os.environ.get("PGHOST", "database_postgres")
PGPORT = os.environ.get("PGPORT", "5432")
PGDATABASE = os.environ.get("PGDATABASE", "planexe")
PGUSER = os.environ.get("PGUSER", "planexe")
PGPASSWORD = os.environ.get("PGPASSWORD", "planexe")
API_KEY = os.environ.get("PLANEXE_DATABASE_WORKER_API_KEY", "")
PORT = int(os.environ.get("PLANEXE_DATABASE_WORKER_PORT", "8002"))

# zstd typically compresses better and faster than gzip, so it's preferred.
# pg_dump >= 16 supports -Z zstd natively; also requires the zstd binary.
_HAS_ZSTD = False
try:
    version_output = subprocess.check_output(["pg_dump", "--version"], text=True)
    pg_major = int(version_output.strip().split()[-1].split(".")[0])
    if pg_major >= 16 and shutil.which("zstd"):
        _HAS_ZSTD = True
except Exception:
    pass
logger.info("Compression: %s (pg_dump %s)", "zstd" if _HAS_ZSTD else "gzip", version_output.strip() if 'version_output' in dir() else "unknown")


class BackupHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthcheck":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")
            return

        if self.path != "/backup":
            self.send_error(404)
            return

        # Simple API key auth if configured
        if API_KEY:
            auth = self.headers.get("X-Database-Worker-Key", "")
            if auth != API_KEY:
                self.send_error(403, "Invalid backup API key")
                return

        if _HAS_ZSTD:
            compress_flag = "zstd:6"
            ext = "sql.zst"
            content_type = "application/zstd"
        else:
            compress_flag = "6"
            ext = "sql.gz"
            content_type = "application/gzip"

        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_planexe_backup.{ext}"

        logger.info("Starting database backup: %s (%s)", filename, "zstd" if _HAS_ZSTD else "gzip")

        env = os.environ.copy()
        env["PGPASSWORD"] = PGPASSWORD

        proc = subprocess.Popen(
            [
                "pg_dump",
                "-h", PGHOST,
                "-p", PGPORT,
                "-U", PGUSER,
                "-d", PGDATABASE,
                "--no-owner",
                "--no-privileges",
                "-Z", compress_flag,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()

        try:
            while True:
                chunk = proc.stdout.read(256 * 1024)
                if not chunk:
                    break
                self.wfile.write(chunk)

            proc.wait()
            if proc.returncode != 0:
                stderr = proc.stderr.read().decode("utf-8", errors="replace")
                logger.error("pg_dump failed (rc=%d): %s", proc.returncode, stderr)
            else:
                logger.info("Backup complete: %s", filename)
        except BrokenPipeError:
            logger.warning("Client disconnected during backup")
            proc.kill()
        finally:
            proc.stdout.close()
            proc.stderr.close()

    def log_message(self, format, *args):
        if "/healthcheck" not in (args[0] if args else ""):
            logger.info(format, *args)


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), BackupHandler)
    logger.info("Backup server listening on port %d", PORT)
    server.serve_forever()
