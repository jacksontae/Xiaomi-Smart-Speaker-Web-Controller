"""Process-wide objects: the speaker transport, the database, sign-in state, the speaker lock and background tasks."""
import asyncio

from server import config
from server.auth import Throttle
from server.config import DATA_PATH
from server.google_signin import GoogleVerifier
from server.passkeys import Challenges
from server.store import Store
from server.transport import make_transport

transport = make_transport(config.settings)
db = Store(DATA_PATH)
login_throttle = Throttle(limit=5, window=300)
google_verifier = GoogleVerifier()
passkey_challenges = Challenges()
cast_lock = asyncio.Lock()
_background = set()


def spawn(coro):
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)
    return task
