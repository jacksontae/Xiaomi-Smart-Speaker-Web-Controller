"""In-memory play queue: play order with shuffle and repeat. No Cast I/O here; app.py drives it."""
import random

REPEAT_MODES = ("off", "all", "one")


class Queue:
    def __init__(self, items, playlist_id=None, name="", start=0, shuffle=False, repeat="off", rng=None):
        if not items:
            raise ValueError("queue needs at least one item")
        if not 0 <= start < len(items):
            raise IndexError("start_index is out of range")
        self.items = list(items)  # snapshot in playlist order; later playlist edits don't touch the queue
        self.playlist_id, self.name, self.repeat = playlist_id, name, repeat
        self.rng = rng or random.Random()
        self.shuffle = False
        self.order = list(range(len(items)))
        self.pos = start
        self.current_url = None  # content_id we loaded for the current item
        self.after_say = False  # move on once the running announcement ends (its track won't be resumed)
        self.failures = 0  # items skipped in a row; the queue stops once every item has failed
        if shuffle:
            self.set_shuffle(True)

    def __len__(self):
        return len(self.items)

    @property
    def current(self):
        return self.items[self.order[self.pos]]

    def _shuffled(self, first=None):
        rest = [i for i in range(len(self.items)) if i != first]
        self.rng.shuffle(rest)
        return rest if first is None else [first, *rest]

    def set_shuffle(self, on):
        current = self.order[self.pos]
        if on:
            self.order, self.pos = self._shuffled(first=current), 0
        else:
            self.order, self.pos = list(range(len(self.items))), current
        self.shuffle = on

    def advance(self, auto):
        """Move to the next item. Returns False when the queue has run out (repeat off)."""
        if auto and self.repeat == "one":
            return True
        if self.pos + 1 < len(self.items):
            self.pos += 1
            return True
        if self.repeat == "off":
            return False
        if self.shuffle and len(self.items) > 1:
            # New order for the next round, but don't play the same track twice in a row.
            last = self.order[self.pos]
            order = self._shuffled()
            if order[0] == last:
                order[0], order[-1] = order[-1], order[0]
            self.order = order
        self.pos = 0
        return True

    def back(self):
        if self.pos > 0:
            self.pos -= 1
        elif self.repeat != "off":
            self.pos = len(self.items) - 1

    def jump(self, index):
        if not 0 <= index < len(self.items):
            raise IndexError("index is out of range")
        self.pos = index

    def peek_next(self):
        """The item auto-advance will most likely play next (for prefetching)."""
        if self.repeat == "one":
            return self.current
        if self.pos + 1 < len(self.items):
            return self.items[self.order[self.pos + 1]]
        return self.items[self.order[0]] if self.repeat == "all" else None

    def summary(self):
        return {
            "playlist_id": self.playlist_id,
            "name": self.name,
            "index": self.pos,
            "length": len(self.items),
            "shuffle": self.shuffle,
            "repeat": self.repeat,
            "items": [self.items[i] for i in self.order],
        }
