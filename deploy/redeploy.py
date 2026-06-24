#!/usr/bin/env python3
"""One-command update of the production server WITHOUT git.

Packages the project, uploads it over SSH, and rebuilds the prod stack.

Usage (from the project root):
    .venv/bin/python deploy/redeploy.py
    # optional: SRV_HOST=1.2.3.4  SRV_USER=deploy  REMOTE_DIR=/opt/idealista

Auth is key-based: SRV_USER must accept your SSH key. Run `ssh SRV_USER@SRV_HOST`
once first so the host key lands in ~/.ssh/known_hosts. Requires `paramiko`.
"""
import os
import subprocess
import sys

import paramiko

HOST = os.environ.get("SRV_HOST", "132.243.221.142")
USER = os.environ.get("SRV_USER", "deploy")
REMOTE_DIR = os.environ.get("REMOTE_DIR", "/opt/idealista")
ARCHIVE = "/tmp/idealista_deploy.tar.gz"
EXCLUDES = [".venv", ".git", "__pycache__", ".pytest_cache", "*.db",
            "data/raw", "exports/*", ".env", "*.tar.gz", "*.sql", "deploy.log"]


def main() -> int:
    print("· packaging project…")
    tar = ["tar", "--disable-copyfile", "--no-xattrs", "-czf", ARCHIVE]
    for e in EXCLUDES:
        tar += ["--exclude", e]
    tar += ["app", "deploy", "sample_data", "migrations", "requirements.txt",
            "requirements-dev.txt", "Dockerfile", "docker-compose.yml",
            "docker-compose.prod.yml", "alembic.ini", "README.md", ".dockerignore"]
    subprocess.run(tar, check=True, stderr=subprocess.DEVNULL)

    c = paramiko.SSHClient()
    c.load_system_host_keys()
    c.set_missing_host_key_policy(paramiko.RejectPolicy())
    c.connect(HOST, username=USER, timeout=30)

    def run(cmd, tmo=900):
        ch = c.get_transport().open_session(); ch.settimeout(tmo); ch.exec_command(cmd)
        out = b""
        while not (ch.exit_status_ready() and not ch.recv_ready() and not ch.recv_stderr_ready()):
            if ch.recv_ready(): out += ch.recv(65536)
            if ch.recv_stderr_ready(): out += ch.recv_stderr(65536)
        return ch.recv_exit_status(), out.decode(errors="replace")

    print("· uploading…")
    sftp = c.open_sftp()
    run(f"mkdir -p {REMOTE_DIR}")
    sftp.put(ARCHIVE, f"{REMOTE_DIR}/deploy.tar.gz")
    sftp.close()

    print("· extracting (keeps .env / data) + rebuilding…")
    rc, out = run(
        f"cd {REMOTE_DIR} && tar xzf deploy.tar.gz && rm deploy.tar.gz && "
        f"docker compose -f docker-compose.prod.yml up -d --build 2>&1 | tail -8"
    )
    print(out)
    print("· stack:")
    print(run(f"cd {REMOTE_DIR} && docker compose -f docker-compose.prod.yml ps "
              f"--format 'table {{{{.Service}}}}\\t{{{{.Status}}}}'")[1])
    c.close()
    print("done." if rc == 0 else f"finished with exit {rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
