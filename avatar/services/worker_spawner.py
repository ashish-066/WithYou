"""Worker spawner for dynamically scaling workers during demo.

Spawns worker processes programmatically to demonstrate auto-scaling.
"""

import asyncio
import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Path to worker directory (relative to avatar service)
WORKER_DIR = Path(__file__).parent.parent.parent / "worker"
WORKER_PYTHON = WORKER_DIR / ".venv" / "bin" / "python"


class WorkerSpawner:
    """Spawns and manages worker processes for demo scaling."""

    def __init__(self):
        self.spawned_workers: dict[str, subprocess.Popen] = {}
        self._worker_ids: dict[str, str] = {}  # pid -> worker_id mapping
        self._lock = asyncio.Lock()

    async def spawn_worker(self) -> str | None:
        """Spawn a single worker process.

        Returns:
            Worker PID as string, or None if failed
        """
        async with self._lock:
            try:
                # Create unique worker ID via environment variable
                import uuid

                worker_id = str(uuid.uuid4())[:8]

                env = os.environ.copy()
                env["WORKER_ID"] = worker_id

                # Spawn worker process - inherit stdout/stderr so we can see logs
                process = subprocess.Popen(
                    [str(WORKER_PYTHON), "worker.py"],
                    cwd=str(WORKER_DIR),
                    env=env,
                    stdout=None,  # Inherit from parent - logs will appear in console
                    stderr=None,  # Inherit from parent
                )

                pid = str(process.pid)
                self.spawned_workers[pid] = process
                self._worker_ids[pid] = worker_id

                logger.info(f"Spawned worker {worker_id} with PID {pid}")
                return pid

            except Exception as e:
                logger.error(f"Failed to spawn worker: {e}")
                return None

    async def spawn_workers(self, count: int) -> list[str]:
        """Spawn multiple worker processes.

        Args:
            count: Number of workers to spawn

        Returns:
            List of worker PIDs
        """
        pids = []
        for _ in range(count):
            pid = await self.spawn_worker()
            if pid:
                pids.append(pid)
            # Small delay between spawns to stagger startup
            await asyncio.sleep(0.2)
        return pids

    async def terminate_worker(self, pid: str) -> bool:
        """Terminate a specific worker.

        Args:
            pid: Process ID to terminate

        Returns:
            True if terminated successfully
        """
        async with self._lock:
            process = self.spawned_workers.get(pid)
            if not process:
                return False

            try:
                worker_id = self._worker_ids.get(pid, "unknown")

                # Send SIGTERM for graceful shutdown
                process.terminate()

                # Wait briefly for graceful exit
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Force kill if not responding
                    process.kill()
                    process.wait()

                del self.spawned_workers[pid]
                self._worker_ids.pop(pid, None)
                logger.info(f"Terminated worker {worker_id} with PID {pid}")
                return True

            except Exception as e:
                logger.error(f"Failed to terminate worker {pid}: {e}")
                return False

    async def terminate_all(self) -> int:
        """Terminate all spawned workers.

        Returns:
            Number of workers terminated
        """
        pids = list(self.spawned_workers.keys())
        terminated = 0

        for pid in pids:
            if await self.terminate_worker(pid):
                terminated += 1

        logger.info(f"Terminated {terminated} workers")
        return terminated

    def get_active_count(self) -> int:
        """Get count of active spawned workers."""
        # Clean up any that have exited
        to_remove = []
        for pid, process in self.spawned_workers.items():
            exit_code = process.poll()
            if exit_code is not None:
                worker_id = self._worker_ids.get(pid, "unknown")
                logger.warning(
                    f"Worker {worker_id} (PID {pid}) exited with code {exit_code}"
                )
                to_remove.append(pid)

        for pid in to_remove:
            del self.spawned_workers[pid]
            self._worker_ids.pop(pid, None)

        return len(self.spawned_workers)

    def get_worker_pids(self) -> list[str]:
        """Get list of active worker PIDs."""
        return list(self.spawned_workers.keys())


# Global spawner instance
worker_spawner = WorkerSpawner()
