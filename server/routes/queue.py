"""The play queue: moving through it, shuffle and repeat."""

from fastapi import HTTPException

from server import playback
from server.access import Who, operator_api, record, viewer_api
from server.playback import play_queue, stop_everything
from server.schemas import JumpBody, QueuePatch

# --- Queue ---

def active_queue():
    if playback._queue is None:
        raise HTTPException(404, "Nothing is queued")
    return playback._queue


async def play_moved(q, who, how):
    record(who, "queue skip", f"{how}: {q.current['title']}")
    if not await play_queue(q):
        raise HTTPException(502, "No playable items left in the queue")
    playback.ensure_queue_watcher()
    return q.summary()


@viewer_api.get("/queue")
async def get_queue():
    return playback._queue.summary() if playback._queue is not None else None


@viewer_api.post("/queue/next")
async def queue_next(who: Who):
    q = active_queue()
    if not q.advance(auto=False):
        raise HTTPException(409, "Already at the last item")
    return await play_moved(q, who, "next")


@viewer_api.post("/queue/prev")
async def queue_prev(who: Who):
    q = active_queue()
    q.back()
    return await play_moved(q, who, "previous")


@viewer_api.post("/queue/jump")
async def queue_jump(body: JumpBody, who: Who):
    q = active_queue()
    try:
        q.jump(body.index)
    except IndexError as e:
        raise HTTPException(400, "index is out of range") from e
    return await play_moved(q, who, "jump")


@operator_api.patch("/queue")
async def update_queue(body: QueuePatch):
    q = active_queue()
    if body.shuffle is not None and body.shuffle != q.shuffle:
        q.set_shuffle(body.shuffle)
    if body.repeat is not None:
        q.repeat = body.repeat
    playback.schedule_prefetch(q)
    return q.summary()


@operator_api.post("/queue/clear", status_code=204)
async def queue_clear(who: Who):
    record(who, "stop", "queue cleared")
    await stop_everything()
