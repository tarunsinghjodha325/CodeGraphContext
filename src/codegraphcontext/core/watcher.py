# src/codegraphcontext/core/watcher.py
import logging
import threading
from pathlib import Path
import typing
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# To avoid circular import, we use a type hint string
# The actual object is passed in __init__
if typing.TYPE_CHECKING:
    from codegraphcontext.tools.graph_builder import GraphBuilder


logger = logging.getLogger(__name__)

class DebouncedEventHandler(FileSystemEventHandler):
    """
    An event handler that debounces events to avoid rapid, repeated processing.
    """
    def __init__(self, graph_builder: "GraphBuilder", debounce_interval=1.5):
        super().__init__()
        self.graph_builder = graph_builder
        self.debounce_interval = debounce_interval
        self.timers = {}

    def _debounce(self, event_path, action):
        """Schedules an action to be performed after a debounce interval."""
        if event_path in self.timers:
            self.timers[event_path].cancel()
        timer = threading.Timer(self.debounce_interval, action)
        timer.start()
        self.timers[event_path] = timer

    def _handle_change(self, event_path):
        """Action to perform when a file is created or modified."""
        logger.info(f"File change detected, updating graph for: {event_path}")
        try:
            path_obj = Path(event_path)
            self.graph_builder.update_file_in_graph(path_obj)
        except Exception as e:
            logger.error(f"Error updating graph for {event_path}: {e}")

    def _handle_deletion(self, event_path):
        """Action to perform when a file is deleted."""
        logger.info(f"File deletion detected, removing from graph: {event_path}")
        try:
            self.graph_builder.delete_file_from_graph(event_path)
        except Exception as e:
            logger.error(f"Error removing {event_path} from graph: {e}")

    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith('.py'):
            self._debounce(event.src_path, lambda: self._handle_change(event.src_path))

    def on_modified(self, event):
        if not event.is_directory and event.src_path.endswith('.py'):
            self._debounce(event.src_path, lambda: self._handle_change(event.src_path))

    def on_deleted(self, event):
        if not event.is_directory and event.src_path.endswith('.py'):
            self._debounce(event.src_path, lambda: self._handle_deletion(event.src_path))

    def on_moved(self, event):
        if not event.is_directory and event.src_path.endswith('.py'):
            self._debounce(event.src_path, lambda: self._handle_deletion(event.src_path))
            self._debounce(event.dest_path, lambda: self._handle_change(event.dest_path))


class CodeWatcher:
    """Manages file system watching in a background thread."""
    def __init__(self, graph_builder: "GraphBuilder"):
        self.graph_builder = graph_builder
        self.observer = Observer()
        self.watched_paths = set()
        self.event_handler = DebouncedEventHandler(self.graph_builder)

    def watch_directory(self, path: str):
        """Starts watching a directory if not already watched."""
        path = str(Path(path).resolve())
        if path in self.watched_paths:
            logger.info(f"Path already being watched: {path}")
            return
        
        self.observer.schedule(self.event_handler, path, recursive=True)
        self.watched_paths.add(path)
        logger.info(f"Started watching for code changes in: {path}")

    def start(self):
        """Starts the observer thread."""
        if not self.observer.is_alive():
            self.observer.start()
            logger.info("Code watcher observer thread started.")

    def stop(self):
        """Stops the observer thread."""
        if self.observer.is_alive():
            self.observer.stop()
            self.observer.join()
            logger.info("Code watcher observer thread stopped.")