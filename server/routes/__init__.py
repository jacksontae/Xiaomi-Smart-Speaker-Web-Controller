"""HTTP and WebSocket endpoints, one module per area of the app.

Each module adds its endpoints to the shared routers in server.access as it is imported, so the imports below fix
the order the routes are matched in (the order they had in the single app.py). Importing any one module of this
package runs this file first, which keeps that order whoever imports first.
"""
# isort: off
from server.routes import accounts  # noqa: F401
from server.routes import members  # noqa: F401
from server.routes import player  # noqa: F401
from server.routes import settings  # noqa: F401
from server.routes import playlists  # noqa: F401
from server.routes import queue  # noqa: F401
from server.routes import radio  # noqa: F401
from server.routes import podcasts  # noqa: F401
from server.routes import files  # noqa: F401
from server.routes import device  # noqa: F401
from server.routes import schedules  # noqa: F401
from server.routes import talk  # noqa: F401
from server.routes import talkie  # noqa: F401
from server.routes import streams  # noqa: F401
from server.routes import web  # noqa: F401
# isort: on
