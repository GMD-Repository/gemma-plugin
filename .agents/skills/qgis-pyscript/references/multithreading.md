# Multithreading & Background Tasks in QGIS

When developing python scripts or plugins for QGIS, running heavy computations on the main application thread will cause the user interface (GUI) to freeze.

As a Senior QGIS Developer, you must determine whether code may run in a background thread by evaluating thread safety, UI interactions, and processing behavior.

---

## 1. Architectural Rules for Threading

1. **GUI Isolation**: Background threads (`QgsTask`, `QThread`, `QRunnable`) **MUST NEVER** access, modify, or call UI elements (`QMessageBox`, `QDialog`, `iface.mapCanvas()`) directly.
2. **Layer Mutability**: Do not start edit sessions, change attribute values, or alter geometries of active QGIS map layers from a background thread.
3. **Communication Pattern**: Use Qt Signals/Slots. Run computations in the thread, emit results/exceptions via a signal, and handle layer modifications or GUI updates in a slot connected to that signal on the Main Thread.
4. **FlagNoThreading**: If thread safety cannot be guaranteed (e.g., specific legacy provider limitations), explicitly explain the risk and use the `FlagNoThreading` flag where applicable.

---

## 2. Processing Algorithms Background Execution

When writing a `QgsProcessingAlgorithm`, QGIS handles multithreading automatically when the tool is run from the Toolbox. You do not need to manually write `QgsTask` inside `processAlgorithm()`.

**Important**: Because algorithms run in the background, you must never use `iface` or PyQt GUI prompts inside the logic.

---

## 3. Subclassing `QgsTask` (The Standard for Plugins)

For complex plugins requiring network requests, downloads, or external system communication without freezing QGIS, subclassing `QgsTask` is the required standard.

```python
import logging
from qgis.core import QgsTask, QgsApplication, Qgis

logger = logging.getLogger("QGIS_Plugin_Task")

class NetworkDownloadTask(QgsTask):
    """
    Background task for downloading resources.
    Implements safe cancellation and error reporting.
    """
    def __init__(self, description: str, urls: list):
        # Allow cancellation by user
        super().__init__(description, QgsTask.CanCancel)
        self.urls = urls
        self.downloaded_count = 0
        self.error_message = None

    def run(self):
        """Runs in the background thread. No GUI or Layer edits here."""
        total = len(self.urls)

        try:
            for idx, url in enumerate(self.urls):
                if self.isCanceled():
                    logger.info("Task canceled by user.")
                    return False

                # Simulate network download
                import time
                time.sleep(1)

                self.downloaded_count += 1
                self.setProgress((idx + 1) / total * 100)

            return True
            
        except Exception as e:
            self.error_message = str(e)
            return False

    def finished(self, result: bool):
        """Runs on the MAIN thread automatically when run() finishes."""
        if result:
            logger.info(f"Successfully downloaded {self.downloaded_count} items.")
            # Safe to interact with iface or map layers here
        else:
            if self.error_message:
                logger.error(f"Download failed: {self.error_message}")
            else:
                logger.warning("Download was canceled.")

# Usage:
# task = NetworkDownloadTask("Downloading assets", ["url1", "url2"])
# QgsApplication.taskManager().addTask(task)
```

---

## 4. Qt Threading with Signals (`QThread`)

If you are developing complex Dock Widgets or Dialogs and need a persistent thread, use `QThread`.

```python
from qgis.PyQt.QtCore import QThread, pyqtSignal
import logging

logger = logging.getLogger("QGIS_Background_Worker")

class AnalysisWorker(QThread):
    # Signals must be class attributes
    progress_updated = pyqtSignal(int)
    analysis_finished = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, data_list):
        super().__init__()
        self.data_list = data_list

    def run(self):
        """Heavy calculations without touching QGIS layers."""
        results = {}
        total = len(self.data_list)

        try:
            for idx, item in enumerate(self.data_list):
                import time
                time.sleep(0.1)  # Simulate work
                results[item] = len(item)

                self.progress_updated.emit(int((idx + 1) / total * 100))

            self.analysis_finished.emit(results)
            
        except Exception as e:
            logger.error(f"Worker Error: {str(e)}")
            self.error_occurred.emit(str(e))

# Main Thread Handling
def handle_results(results: dict):
    """Slot that runs on the main thread."""
    logger.info(f"Processing results safely: {results}")

# worker = AnalysisWorker(["FeatureA", "FeatureB"])
# worker.analysis_finished.connect(handle_results)
# worker.start()
```
