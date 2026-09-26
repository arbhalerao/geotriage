import logging
import os
import signal
import threading

# importing the task module registers every @task with the queue registry
import worker.tasks  # noqa: F401
from worker.queue.scheduler import scheduler_loop
from worker.queue.worker import worker_loop

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("worker.run")


def sweep_scratch() -> None:
    from core.db.sync import get_session
    from pipeline.scratch import sweep

    try:
        with get_session() as db:
            log.info("swept %d leftover scratch folders", sweep(db))
    except Exception:  # noqa: BLE001 — leftovers are wasted space, never a reason not to start
        log.warning("couldn't sweep the scratch volume", exc_info=True)


def main() -> None:
    concurrency = int(os.getenv("WORKER_CONCURRENCY", "4"))
    sweep_scratch()
    stop_event = threading.Event()

    def _handle_signal(signum, _frame):
        log.info("received signal %s, shutting down", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    threads = [threading.Thread(target=worker_loop, args=(stop_event, i), name=f"worker-{i}") for i in range(concurrency)]
    threads.append(threading.Thread(target=scheduler_loop, args=(stop_event,), name="scheduler"))

    log.info("starting %d worker threads + scheduler", concurrency)
    for t in threads:
        t.start()

    while not stop_event.wait(1.0):
        pass

    for t in threads:
        t.join(timeout=30)
    log.info("worker shutdown complete")


if __name__ == "__main__":
    main()
