import asyncio

from fastapi import APIRouter, WebSocket

from api.live import hub

router = APIRouter(tags=["live"])


@router.websocket("/live")
async def live_updates(websocket: WebSocket):
    """
    one-way: the server announces changes and the browser refetches what it has on screen
    the protocol is `{"type": "changes", "changes": [...]}` or `{"type": "resync"}`
    """
    await websocket.accept()
    queue = hub.subscribe()

    async def send():
        while True:
            await websocket.send_json(await queue.get())

    async def until_disconnect():
        # the browser never sends anything, but receiving is how a disconnect gets noticed
        while (await websocket.receive())["type"] != "websocket.disconnect":
            pass

    tasks = {asyncio.create_task(send()), asyncio.create_task(until_disconnect())}
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        hub.unsubscribe(queue)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
