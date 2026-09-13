# GUI 框架遷移：CustomTkinter → PySide6

## Context

目前 [gps_app.py](../gps_app.py) 是單一 1539 行檔案、用 CustomTkinter 實作。CLAUDE.md 裡記錄了大量因 tkinter/CTk 本身限制而生的手刻 workaround（虛擬化列表、DPI/多螢幕還原用 ctypes 呼叫、按鈕停用狀態要手動改色、捲軸顯示/隱藏要碰私有屬性等），這些都被使用者標記為「已知風險點」。使用者希望重構 GUI 並已選定 PySide6 作為新框架，目的是用 Qt 原生元件（QTableView 虛擬化、QSS 主題、QScreen API）取代這些手刻邏輯，降低維護風險。

這是全面重寫 UI 層，領域邏輯（路線內插、最愛存讀、KML 解析、連線狀態機）幾乎原封不動搬過去。

## 專案結構調整

沿用使用者全域 coding-style 規範（多檔案優於單一大檔、200-400 行、800 行軟上限），新架構改為套件形式，不再是單一檔案：

```
gps_qt/
├── __init__.py
├── main.py              # entry point：建立 QApplication + qasync event loop、啟動主視窗
├── theme.py             # THEMES dict、QSS 產生器、字級/尺寸常數（對應舊檔 _pair/THEMES 區塊）
├── geo.py               # haversine()、interpolate_points()（原封不動搬移）
├── persistence.py       # load/save favorites、settings、KML 解析（原封不動搬移，僅去除 tkinter 相依）
├── window_geometry.py   # 視窗位置記憶、多螢幕還原（改用 QScreen API，取代 ctypes）
├── session.py           # GPSSession：_session_main/_walk_route/_walk_pin 狀態機（沿用 pending_action 設計）
├── models.py            # RouteTableModel(QAbstractTableModel)、FavoritesListModel（若採 model 化）
└── widgets/
    ├── main_window.py   # MainWindow(QMainWindow)：整體版面、responsive layout、log 面板
    ├── route_panel.py   # 路線模式面板 + QTableView + delegate（虛擬化表格 + 刪除按鈕）
    ├── pin_panel.py     # 固定定位模式面板
    └── favorites_panel.py  # 最愛清單（QListWidget + 自訂 item widget）
```

`gps_app.py` 保留不動，直到新版通過真機驗證（Phase 7）才刪除/取代，並更新 [run.bat](../run.bat) 與 [CLAUDE.md](../CLAUDE.md) 指向新的進入點。

## 關鍵技術決策

1. **非同步整合用 `qasync`，不用背景 thread。**
   目前 `_ensure_session_thread()` 開一條 thread 跑 `asyncio.run()`，UI 更新靠 `self.after(0, callback)` 排回主執行緒（gps_app.py:1394-1415）。`qasync` 讓 asyncio 事件迴圈直接跑在 Qt 事件迴圈的同一條 thread 上，`_session_main`/`_walk_route`/`_walk_pin` 的 async/await 邏輯幾乎不用改，但**不再需要 `self.after(0, ...)` 這層 marshalling**——協程可以直接呼叫 UI 更新方法。這比原本設想的「換成 signal/slot」更省工。
   `main.py` 用 `qasync.QEventLoop` 包住 `QApplication`，`asyncio.set_event_loop(loop)`；按下開始時用 `asyncio.ensure_future(session.run())` 建立 task（存起來供停止/斷線時取消）。

2. **路線表格：`QTableView` + `QAbstractTableModel` + 自訂 delegate。**
   取代 gps_app.py:1146-1275 整段手刻虛擬化（`ROUTE_ROW_POOL`/`place()`/`_route_spacer`）。Model 只存資料（`self.route` 的 list），view 原生只 render 可見列。
   座標欄需要可編輯（對應原本 `CTkEntry` + `_on_edit`）：用 `Qt.ItemIsEditable` flag，`setData()` 觸發時更新 `self.route`（不需要 `_route_rebinding` 那套防呆，因為 model/view 分離後不會有「換綁資料觸發舊列 callback」的問題）。
   刪除按鈕欄：用自訂 `QStyledItemDelegate` 畫一個按鈕圖示、在 `editorEvent()` 攔截點擊觸發刪除，**不要**用 `setIndexWidget()`（那會退化成又要手動管理 widget 生命週期）。

3. **主題系統：QSS stylesheet 取代 tuple 色票。**
   `theme.py` 保留 `THEMES = {"light": {...}, "dark": {...}}` 的 dict 結構（人看得懂、好維護），但改成產生一段 QSS 字串（用 f-string template），透過 `app.setStyleSheet(qss)` 套用。切換主題只是重新產生字串再 `setStyleSheet()`，Qt 會自動重畫所有 widget，不需要銷毀重建（維持原本「切主題不重建 UI」的優點）。

4. **視窗幾何 / DPI / 多螢幕：改用 QScreen API。**
   取代 gps_app.py:141-200 的 `ctypes` + `MonitorFromPoint` + `_logical_to_physical`。Qt6 預設開啟 High-DPI scaling，`QWidget.geometry()`/`QScreen.availableGeometry()` 都是邏輯像素，直接用 `QGuiApplication.screenAt(QPoint(x, y))` 判斷座標是否落在任何螢幕上，回傳 `None` 就代表無效，不用手動做實體/邏輯像素換算。
   存讀邏輯（`gps_settings.json` 的 `"window"` 欄位格式）不變，`window_geometry.py` 提供 `restore(window, settings)` / `remember(window) -> dict` 兩個函式，行為對應原本 `_restore_window_geometry`/`_remember_window_geometry`/`_save_window_geometry`。

5. **捲動與響應式版面：`QScrollArea` + 手動 resize 判斷寬度。**
   取代 `CTkScrollableFrame` 手動控制捲軸顯示（gps_app.py:296-314）；`QScrollArea` 預設行為就是內容塞得下就不顯示捲軸，不需要碰任何私有屬性。
   兩欄/單欄切換沿用原本邏輯：`MainWindow.resizeEvent()` 依寬度是否超過 `WIDE_LAYOUT_BREAKPOINT` 決定用 `QHBoxLayout` 並排還是 `QVBoxLayout` 堆疊（對應 gps_app.py:588-604 的 `_apply_responsive_layout`）。

6. **最愛清單：`QListWidget` + 自訂 item widget。**
   對應 gps_app.py:982-1043 的 `_refresh_fav_list`。每個項目是一個小 widget（icon label + name label + preview label + 刪除按鈕），用 `setItemWidget()` 掛到 `QListWidgetItem` 上（最愛清單通常項目數少，不像路線表格要處理數千筆，這裡不需要虛擬化，維持原本做法即可）。
   名稱過長截斷：用 `QFontMetrics.elidedText()` 原生函式取代手刻的 `elide_to_width()` 二分搜尋（gps_app.py:277-294）。

7. **按鈕狀態：QSS `:disabled` 偽類 + `setEnabled()`。**
   取代 `_set_btn_enabled`/`enabled_bg`/`enabled_fg` 那套手動換色（gps_app.py:928-953）。四顆控制按鈕的啟用邏輯（依 `pending_action`/`mode` 推導）搬到 `session.py` 或 `main_window.py` 的 `sync_button_states()`，純邏輯部分不變，只是視覺交給 QSS。

## 直接搬移、邏輯不變的部分

- `haversine()` / `interpolate_points()` → `geo.py`，純函式原封不動。
- `load_favorites()` / `save_favorites()` / `load_settings()` / `save_settings()` / `load_saved_route()` / `parse_kml_route()` → `persistence.py`，僅需確認沒有 import tkinter 相依（目前看起來沒有）。
- `_session_main()` / `_walk_route()` / `_walk_pin()` 的狀態機邏輯（`pending_action` 驅動）→ `session.py` 的 `GPSSession` class，`self.after(0, x, *a)` 全部改成直接呼叫（見決策 1）。

## 依賴變更

`requirements.txt` 新增：
```
PySide6>=6.7
qasync>=0.27
```
`customtkinter` 移除（遷移完成、確認 `gps_app.py` 刪除後再移除，過渡期兩者並存）。

## 實作階段（每階段結束都可獨立驗證）

1. **骨架**：`main.py` + `MainWindow` 空視窗、`theme.py` QSS 套用、`window_geometry.py` 還原/記憶（含多螢幕）。驗證：開關程式、拖到副螢幕、切主題，行為對齊舊版。
2. **領域邏輯搬移**：`geo.py`、`persistence.py`，寫一個小腳本跑過既有 `gps_favorites.json`/`gps_settings.json` 確認讀寫格式相容。
3. **固定定位模式**（最簡單路徑，優先驗證 qasync 整合）：`pin_panel.py` + `session.py` 的 `_walk_pin` 對應邏輯 + 開始/停止按鈕。驗證：接真機跑一次固定定位全流程。
4. **路線模式**：`route_panel.py`（QTableView + model + delegate）+ `_walk_route` 對應邏輯 + 循環模式。驗證：長路線（沿用 446 點的既有測試路線）捲動效能、編輯座標、刪除點、返回/循環都正確。
5. **最愛清單**：`favorites_panel.py` + KML 匯入。驗證：新增/載入/刪除/重新命名 pin 和 route 兩種最愛。
6. **響應式版面 + 執行日誌面板**：寬窄切換、日誌高度隨視窗高度調整。
7. **收尾**：對照 CLAUDE.md 現有行為逐項比對（深色/淺色、按鈕停用視覺、視窗最大化順序等），接真機完整跑一輪四個按鈕（開始/返回/停止/恢復真實定位），確認無誤後刪除 `gps_app.py`、更新 `run.bat` 與 `CLAUDE.md`。

## 驗證方式

沒有既有測試套件，全靠手動驗證（與現有專案慣例一致）。每個階段都要求：
1. 啟動 `python -m gps_qt.main` 確認無 import/執行期錯誤。
2. 依該階段涉及的功能，對照 CLAUDE.md 記錄的既有行為手動操作一輪。
3. 第 3、4、7 階段需要接實體 iPhone + tunneld 驗證定位模擬（依 CLAUDE.md「常用指令」章節的步驟）。

---

> 註：此文件為 Claude Code Plan Mode 於 2026-09-12 產生的原始遷移計畫存檔，複製自
> `~/.claude/plans/glowing-knitting-wigderson.md`，供專案內留存參考。實際實作進度與
> 現況請以 [CLAUDE.md](../CLAUDE.md) 的「gps_qt/（PySide6 重寫版）」章節為準——部分細節
> （例如主題系統改用 qt-material 而非自寫 QSS）在實作過程中依使用者指示調整過，與本文件
> 原始決策不完全一致。
