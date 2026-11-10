from PySide6.QtGui import QUndoCommand


class Change(QUndoCommand):
    """A validated project replacement, including selection-independent edit data."""

    def __init__(self, label, before, after, restore):
        super().__init__(label)
        self.before, self.after, self.restore = before, after, restore

    def redo(self):
        self.restore(self.after)

    def undo(self):
        self.restore(self.before)


class MoveEdge(QUndoCommand):
    def __init__(self, window, track, edge, old_time, new_time):
        super().__init__("Move edge")
        self.window = window
        self.track = track
        self.edge = edge
        self.old_time = old_time
        self.new_time = new_time

    def apply(self, time):
        w = self.window
        track = w.p.track(self.track)
        if track.kind == "clock":
            track.phase = time
        else:
            next(e for e in track.edges if e.id == self.edge).t = time
        item = w.scene.items_by_id.get(track.id)
        if item:
            item.update()
        w.scene.edge = None
        if w.p.notes or track.kind == "clock":
            w.view.viewport().update()
        w.inspector()
        w.status()

    def redo(self):
        self.apply(self.new_time)

    def undo(self):
        self.apply(self.old_time)
