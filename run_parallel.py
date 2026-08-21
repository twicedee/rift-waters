"""
run_parallel.py

Launches multiple main.py commands as separate subprocesses so acquisitions
(e.g. Sentinel-1 + DEM) run concurrently instead of sequentially.
"""

import subprocess
import sys
from pathlib import Path

# Each entry describes one main.py invocation. Add/remove jobs here.
JOBS = [
    {
        "name": "sentinel1_bogoria",
        "args": [
            "acquire", "--satellites", "sentinel1",
            "--region", "turukana",
            "--start_date", "2026-01-01",
            "--end_date", "2026-01-31",
        ],
    },
    {
        "name": "dem_bogoria",
        "args": [
            "acquire_dem",
            "--region", "bogoria",
            "--start_date", "2026-01-01",
            "--end_date", "2026-01-31",
        ],
    },
]


def build_command(job):
    """Turn a job dict into the argv list subprocess needs:
    [python, main.py, <subcommand>, ...args]."""
    return [sys.executable, "main.py", *job["args"]]


def launch_job(job):
    """Start one job as a background process and return the Popen handle immediately.

    Popen starts the process and returns without waiting for it to finish —
    that's what lets multiple jobs run at the same time. stdout/stderr are
    captured (and merged via STDOUT) so we can print each job's output as a
    clean block later, instead of several processes interleaving raw text
    on screen at once.
    """
    print(f"▶ starting {job['name']}: {' '.join(job['args'])}")
    process = subprocess.Popen(
        build_command(job),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=Path(__file__).parent,  # so main.py resolves regardless of caller's cwd
    )
    return process


def wait_for_jobs(processes):
    """Block until every process finishes, then report its output and exit code.

    process.communicate() waits for that one process to terminate and returns
    its full captured output. Because this loop runs *after* all Popen calls
    in main(), every job is already running in the background by the time we
    start waiting — we're not blocking on job 1 before job 2 even starts.
    """
    results = {}
    for name, process in processes.items():
        stdout, _ = process.communicate()
        results[name] = process.returncode
        status = "✅ done" if process.returncode == 0 else f"❌ failed (exit {process.returncode})"
        print(f"\n--- {name}: {status} ---")
        print(stdout)
    return results


def main():
    processes = {job["name"]: launch_job(job) for job in JOBS}
    results = wait_for_jobs(processes)

    failed = [name for name, code in results.items() if code != 0]
    if failed:
        print(f"\n⚠️ {len(failed)} job(s) failed: {', '.join(failed)}")
        sys.exit(1)
    print("\n✅ all jobs completed successfully")


if __name__ == "__main__":
    main()