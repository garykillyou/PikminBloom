"""路徑解析：把「隨附的唯讀資源」與「可寫入的使用者資料」分成兩條路徑。

直接跑原始碼時這兩者都在專案根目錄，沒有分開的必要；但打包成 exe
（PyInstaller onedir）之後就必須分開：

- 隨附資源（`web/` 底下的地圖頁面與 Leaflet）位於程式目錄，安裝到
  `Program Files` 之後是唯讀的，而且升級時整個目錄會被覆蓋掉。
- 使用者資料（最愛、設定）則放在 exe 所在的資料夾，跟著整包一起搬（隨身碟、
  複製到另一台機器都不會掉設定）。**注意**：把程式裝進 `Program Files` 這類
  需要管理員權限才能寫入的位置時，設定會存不起來，請放在使用者自己的資料夾底下。

未凍結時兩者都回到專案根目錄，開發時的行為與打包前完全相同（也因此不需要
替既有的 JSON 檔做搬家）。
"""

import os
import sys

_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))


def is_frozen():
    """是否為 PyInstaller 打包後的執行檔。"""
    return bool(getattr(sys, "frozen", False))


def executable_dir():
    """exe 所在的資料夾；未凍結時是專案根目錄。"""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.normpath(os.path.join(_PACKAGE_DIR, ".."))


def resource_path(*parts):
    """隨附的唯讀資源，路徑相對於 `gps_qt` 套件目錄。

    onedir 模式下 `sys._MEIPASS` 指向 `_internal`，資源打包在其下的 `gps_qt/`，
    因此兩種情況下傳入的相對路徑寫法完全一樣。
    """
    if is_frozen():
        base = os.path.join(getattr(sys, "_MEIPASS", executable_dir()), "gps_qt")
    else:
        base = _PACKAGE_DIR
    return os.path.normpath(os.path.join(base, *parts))


def data_file(name):
    """使用者資料檔（最愛、設定）的完整路徑：一律放在 exe 所在的資料夾。"""
    return os.path.normpath(os.path.join(executable_dir(), name))
