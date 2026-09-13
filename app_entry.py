"""PyInstaller 打包用的主程式進入點（對應 dist 裡的 PinDrift.exe）。

PyInstaller 只吃「腳本」不吃「模組」，所以不能直接指定 `gps_qt.main`，
需要這個薄薄的一層。真正的邏輯都在 gps_qt/main.py。

`freeze_support()` 必須在任何其他 import 之前呼叫：凍結後的程式若有子行程
用 spawn 方式啟動，會重新執行這個腳本，沒先呼叫就會無限遞迴開新視窗。
"""

import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()

    from gps_qt.main import main

    main()
