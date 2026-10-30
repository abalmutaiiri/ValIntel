"""Signal bridge between worker threads and Qt event loop."""
from PySide6.QtCore import QObject, Signal

class Bridge(QObject):
    """Cross-thread delivery. Qt executes receivers on the GUI thread."""
    event = Signal(object)
    portrait = Signal(str, object)
    catalog = Signal(object)
