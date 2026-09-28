"""Every default-branch change to every file, with blob ids, from the read-only mirrors.

    cd analysis && python3 report/messages/gitscan.py

Writes messages.sqlite `blobs` (repo, sha, ts, day, subject, author, path, old_blob, new_blob,
status, n_files). git.commit_files has paths but no blob ids, and "the same content landed
in several repos" needs the blob. First-parent only, so a merge commit's row is its diff
against the previous main (--diff-merges=first-parent), matching one row per PR.
"""
import os
import sqlite3
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
MIRRORS = os.path.join(PLUGIN, ".analysis", "data", "mirrors")
DB = os.path.join(PLUGIN, ".analysis", "data", "messages.sqlite")


def scan(repo):
    out = subprocess.run(
        ["git", "-C", os.path.join(MIRRORS, repo + ".git"), "log", "--first-parent", "--diff-merges=first-parent",
         "--raw", "--no-renames", "--no-abbrev", "--format=@@%H\x1f%cI\x1f%an\x1f%s", "HEAD"],
        capture_output=True, text=True, check=True).stdout
    rows, cur, files = [], None, []

    def flush():
        if cur:
            for f in files:
                rows.append((*cur, *f, len(files)))

    for line in out.splitlines():
        if line.startswith("@@"):
            flush()
            sha, ts, author, subject = line[2:].split("\x1f", 3)
            cur, files = (repo, sha, ts, ts[:10], subject, author), []
        elif line.startswith(":"):
            meta, path = line.split("\t", 1)
            _, _, old, new, status = meta.split()
            files.append((path, old, new, status))
    flush()
    return rows


def main():
    con = sqlite3.connect(DB)
    con.execute("DROP TABLE IF EXISTS blobs")
    con.execute("CREATE TABLE blobs (repo TEXT, sha TEXT, ts TEXT, day TEXT, subject TEXT, author TEXT, path TEXT, "
                "old_blob TEXT, new_blob TEXT, status TEXT, n_files INTEGER)")
    for m in sorted(os.listdir(MIRRORS)):
        if m.endswith(".git"):
            rows = scan(m[:-4])
            con.executemany("INSERT INTO blobs VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
            print(m, len(rows))
    con.execute("CREATE INDEX blobs_path ON blobs(path)")
    con.execute("CREATE INDEX blobs_new ON blobs(new_blob)")
    con.commit()


if __name__ == "__main__":
    main()
