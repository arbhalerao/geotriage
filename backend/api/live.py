import asyncio
import json
import logging
from contextlib import asynccontextmanager

import asyncpg
from sqlalchemy.engine import make_url

from core.config import settings

log = logging.getLogger(__name__)

CHANNEL = "geotriage_changes"

# a running workflow touches thousands of rows, and a browser only needs to hear about each one once per window
FLUSH_SECONDS = 0.5
# past this, naming every row costs more than telling the browser to refetch what it has on screen
MAX_BATCH = 500
# a client this far behind is told to resync instead of being buffered for without limit
CLIENT_BACKLOG = 32
KEEPALIVE_SECONDS = 30.0
RECONNECT_SECONDS = 5.0

RESYNC = {"type": "resync"}


def libpq_dsn(url: str) -> str:
    """asyncpg takes a plain postgresql:// DSN, not a SQLAlchemy URL naming its driver"""
    return make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)


def parse_notification(payload: str) -> dict | None:
    """None for anything that isn't a change, so a stray NOTIFY on the channel can't break the listener"""
    try:
        change = json.loads(payload)
    except ValueError:
        return None
    if not isinstance(change, dict) or not isinstance(change.get("topic"), str):
        return None
    return change


class Hub:
    """
    coalesces changes and fans them out to every connected browser

    one per process, each process running its own listener,
    so adding API replicas needs no coordination between them
    """

    def __init__(self, max_batch: int = MAX_BATCH, backlog: int = CLIENT_BACKLOG):
        self._max_batch = max_batch
        self._backlog = backlog
        self._clients: set[asyncio.Queue] = set()
        # keyed by canonical JSON, so the same row changing twice in a window is announced once
        self._pending: dict[str, dict] = {}

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._backlog)
        self._clients.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._clients.discard(queue)

    def publish(self, change: dict) -> None:
        self._pending[json.dumps(change, sort_keys=True)] = change

    def flush(self) -> None:
        if not self._pending:
            return
        changes = list(self._pending.values())
        self._pending.clear()
        self.broadcast(RESYNC if len(changes) > self._max_batch else {"type": "changes", "changes": changes})

    def broadcast(self, message: dict) -> None:
        for queue in self._clients:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                # whatever it hasn't read yet is superseded by a full refetch,
                # so a slow client stays connected without the backlog growing
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait(RESYNC)

    async def run(self) -> None:
        while True:
            await asyncio.sleep(FLUSH_SECONDS)
            self.flush()


async def listen(hub: Hub) -> None:
    """
    holds one dedicated connection outside the pool, because LISTEN is state on that connection

    NOTIFY isn't queued for a listener that isn't there,
    so every (re)subscribe tells the browsers to resync whatever they missed in between
    """
    while True:
        conn = None
        try:
            conn = await asyncpg.connect(libpq_dsn(settings.DATABASE_URL))
            lost = asyncio.Event()
            conn.add_termination_listener(lambda _conn: lost.set())
            await conn.add_listener(CHANNEL, lambda _conn, _pid, _channel, payload: _on_notify(hub, payload))
            hub.broadcast(RESYNC)
            log.info("live: listening on %s", CHANNEL)
            while not lost.is_set():
                try:
                    await asyncio.wait_for(lost.wait(), timeout=KEEPALIVE_SECONDS)
                except TimeoutError:
                    # a half-open connection is never reported closed, only found out by sending over it
                    await asyncio.wait_for(conn.execute("SELECT 1"), timeout=KEEPALIVE_SECONDS)
            log.warning("live: listener connection closed, reconnecting in %.0fs", RECONNECT_SECONDS)
        except Exception:  # noqa: BLE001 — the listener must outlive any database outage
            log.warning("live: listener lost its connection, retrying in %.0fs", RECONNECT_SECONDS, exc_info=True)
        finally:
            if conn is not None:
                conn.terminate()
        await asyncio.sleep(RECONNECT_SECONDS)


def _on_notify(hub: Hub, payload: str) -> None:
    change = parse_notification(payload)
    if change is None:
        log.warning("live: ignoring malformed notification %r", payload[:200])
        return
    hub.publish(change)


@asynccontextmanager
async def running(hub: Hub):
    tasks = [asyncio.create_task(listen(hub)), asyncio.create_task(hub.run())]
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


hub = Hub()
