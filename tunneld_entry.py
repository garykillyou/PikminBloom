"""PyInstaller 打包用的 tunneld 進入點（對應 dist 裡的 PinDrift-tunneld.exe）。

刻意跟主程式分成兩個執行檔：tunneld 要以系統管理員身分執行、而且是 console
模式（使用者看得到它在跑、也看得到錯誤訊息），主程式則是一般權限的視窗程式。
兩者共用同一個 `_internal` 資料夾，不會把相依套件打包兩份。
"""

import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()

    from gps_qt.tunneld import run_cli

    sys.exit(run_cli() or 0)
