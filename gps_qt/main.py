"""程式進入點：建立 QApplication + qasync 事件迴圈，啟動主視窗。

qasync 讓 asyncio 事件迴圈直接跑在 Qt 事件迴圈的同一條 thread 上，
GPSSession 的 async/await 狀態機因此不需要背景 thread。
"""

import asyncio
import sys

from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

from .widgets.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = MainWindow()  # noqa: F841 保留參照，避免被 GC

    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
