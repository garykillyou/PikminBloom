# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 專案概述

單一檔案 Python/Tkinter 桌面工具，透過 `pymobiledevice3` 模擬 iPhone（iOS 26）的 GPS 定位，
免越獄、免 iTunes，僅需 USB 連線。整個應用程式邏輯都在 [gps_app.py](gps_app.py) 一個檔案中，
沒有其他模組、套件或子目錄。執行期間會在同目錄產生兩個 JSON 狀態檔：`gps_favorites.json`
（最愛地點/路線）與 `gps_settings.json`（目前僅存主題偏好）。

## 常用指令

```bash
# 安裝相依套件
pip install -r requirements.txt

# 執行前，需先在「系統管理員」的終端機啟動 tunneld（建立 iOS 26 的 RemoteXPC 加密通道）
python -m pymobiledevice3 remote tunneld

# 另開一般終端機執行 App
python gps_app.py
```

也可以雙擊 [run.bat](run.bat) 啟動（用 `pythonw` 執行，不顯示主控台視窗，啟動後 cmd 視窗會自動關閉，只留下程式視窗）。

目前專案沒有測試、lint 或 build 設定（無 test/CI/lint 相關檔案）。

## 架構重點

### 執行流程（連接 iPhone 的關鍵鏈路，長連線架構）
1. `tunneld` 必須以系統管理員權限先啟動（`python -m pymobiledevice3 remote tunneld`），建立 iOS 26 的 RemoteXPC 通道。
2. 按「開始模擬」後，`_ensure_session_thread()` 只會在沒有存活中的 `self.session_thread` 時才另開一條長駐背景執行緒執行 `_run_session()`（`asyncio.run(self._session_main())`）；後續按「停止」「返回」都**不會**重開執行緒或重新連線，只是改變 `self.pending_action` 這個共享狀態（`"forward" | "reverse" | "pause" | "disconnect"`），由 `_session_main()` 內的 while 迴圈讀取並分派動作。
3. `_session_main()` 用 `async with DvtProvider(rsd) as dvt, LocationSimulation(dvt) as sim:` 開一次連線後就常駐在 while 迴圈裡，直到 `pending_action == "disconnect"`（使用者按「恢復真實定位」）才 `break` 出迴圈、呼叫 `sim.clear()` 並讓 `async with` 關閉連線——恢復真實 GPS 只會在明確斷線時發生，單純停止/返回都仍保持模擬連線在目前座標。
4. 座標注入本身仍是 `sim.set(lat, lon)`，只是呼叫位置搬到 `_walk_route()` / `_walk_pin()` 這兩個由 `_session_main()` 依 `pending_action` 呼叫的協程裡。

### 兩種模式（由 `self.mode` StringVar 控制，動作由 `self.pending_action` 驅動）
- **路線模式（route）**：`_walk_route(sim, direction)` 中 `direction=1` 往終點走、`direction=-1` 往起點走回去（「返回」功能，由 `_reverse()` 觸發，設定 `pending_action = "reverse"`）。`interpolate_points()` 依 `haversine()` 算出的距離與設定速度（UI 以 km/h 輸入，經 `_speed_ms()` 換算成 m/s）把路線切成每秒一個內插點；目前走到第幾個內插點記錄在 `self.point_idx`，中斷（停止/切換方向/斷線）時會停在原點，之後從該點繼續。支援 `loop_var` 循環模式（只由「開始」的 `direction=1` 啟動）：走到終點後在同一個 `_walk_route()` 內把 `direction` 反向、來回往復（頭→尾→頭→尾…），中途被中斷才會結束。
- **固定定位模式（pin）**：`_walk_pin(sim)` 呼叫一次 `sim.set(lat, lon)` 後立刻把 `pending_action` 設回 `"pause"`，讓外層 while 迴圈進入 `await asyncio.sleep(0.2)` 的閒置分支，藉此在同一條長連線上「保持」定位，直到使用者按「停止」（其實已經是 pause 狀態，UI 只更新按鈕）或「恢復真實定位」。

### 執行緒與非同步整合（長連線 + 狀態機，取代舊版每次都重連的做法）
- 背景執行緒只在需要時建立一次（見上），此後「開始」「停止」「返回」「恢復真實定位」四個按鈕全部只是寫入 `self.pending_action` 這個跨執行緒共享變數，實際動作都在同一個 `_session_main()` 協程的 while 迴圈裡依序處理，不會重新建立 `DvtProvider`/`LocationSimulation`。
- 背景執行緒中若要更新 Tkinter UI（進度條、日誌、按鈕狀態），一律要透過 `self.after(0, ...)` 排回主執行緒，不可直接操作 widget。
- 四顆控制按鈕（開始/返回/停止/恢復真實定位）的狀態統一由 `_sync_btn_states()` 依 `self.pending_action` 與 `self.mode` 推導，不再各自散落 `config(state=...)`；`_on_paused()`（暫停/返回中斷後）與 `_on_session_ended()`（`_run_session()` 的 `finally` 區塊，連線真正結束後）兩個 callback 都只是呼叫它，`_update_return_btn_state()` 另外控制「返回」按鈕只在路線模式且未在返回/斷線中時可用。`_build_ui()` 尾端也會呼叫 `_sync_btn_states()`，所以切換主題整個重建 UI 之後狀態不會退回預設值。
- 實際切換單一按鈕要走 `_set_btn_enabled(btn, enabled)`，不要直接 `config(state=...)`：tkinter 的 `state="disabled"` 只會換文字色、背景色完全不動，會讓停用中的「停止」仍是滿版 `DANGER` 底而看起來比可按的按鈕更醒目。每顆按鈕「啟用時」的顏色在 `_build_ui()` 建立後登記在 `btn.enabled_bg` / `btn.enabled_fg`，停用時一律換成 `DISABLED_BG` + `DISABLED_TEXT`（透過 `disabledforeground`）。
- 新增/修改任何動作（`pending_action` 的新值）時，需同步確認：(a) `_session_main()` 的 if/elif 分派邏輯、(b) 對應的 `_walk_*()` 協程如何在動作被外部改變時中斷並保留 `self.point_idx`、(c) 觸發該動作的按鈕要如何重置其他按鈕狀態。

### 最愛地點（Favorites）
- 儲存在執行檔同目錄的 `gps_favorites.json`（`FAVORITES_FILE`），由 `load_favorites()` / `save_favorites()` 讀寫，內容是 list of dict，`type` 欄位為 `"pin"` 或 `"route"`。
- UI 清單（`_refresh_fav_list`）與載入邏輯（`_load_fav`）都靠這個 `type` 欄位分派要切到哪個模式、要填哪些欄位；新增最愛欄位時要同步確認存檔格式與讀取端都對得起來。
- 路線最愛除了手動輸入座標（`_save_current_route_as_fav`）外，也可從 KML 檔案匯入（`_import_kml_as_fav` → `parse_kml_route()`）：解析第一條 `LineString` 作為路線座標，並用起訖點附近（約 50 公尺內）的 `Point` 名稱自動當作起訖點備註，其餘中間點備註留空。

### 主題系統（深色 / 淺色）
- 兩組色票集中定義在檔案開頭的 `THEMES` dict（`"dark"` / `"light"`），`apply_theme(name)` 會把對應色票寫入模組層級的全域變數（`BG`/`BG2`/`BG3`/`HOVER`/`ACCENT`/`ACCENT2`/`DANGER`/`TEXT`/`TEXT2`/`TEXT_ON_ACCENT`/`TEXT_ON_ACCENT2`），其中 `TEXT_ON_ACCENT` 專用於亮底色（`ACCENT`/`DANGER`）、`TEXT_ON_ACCENT2` 專用於暗底色（`ACCENT2`/`HOVER`），兩者不可互換；另有 `DISABLED_BG`/`DISABLED_TEXT` 專供按鈕停用狀態使用（亮度刻意壓在 `BG3` 之下，讓停用按鈕退到「可按的次要按鈕」之後）。以上全域變數供整份檔案的 UI 建構函式讀取。
- 目前套用的主題名稱存在 `self.theme_name`，並持久化在 `gps_settings.json`（`load_settings()` / `save_settings()`）；啟動時讀取上次的偏好，找不到或值不合法就 fallback 回 `"dark"`。
- `_toggle_theme()` 切換主題時，因為顏色是模組全域變數而非 widget 屬性，唯一能讓所有既有 widget 換色的方式是整個銷毀重建：先暫存目前輸入框/勾選狀態，`apply_theme()` 換色後銷毀 `self.container` 並重新呼叫 `_build_scroll_container()` + `_build_ui()`，最後再把暫存的狀態寫回新建立的 widget。新增任何有「使用者輸入中狀態」的欄位時，記得同步加進這段暫存/還原流程，否則切換主題會遺失使用者輸入。

### 視窗捲動與響應式版面
- 整個視窗內容包在一個可捲動的 `Canvas` + `Frame`（`_build_scroll_container()` 建立 `self.canvas`/`self.scroll_frame`），捲軸（`self.scrollbar`）只有在內容高度超過可視區域時才會 `pack()` 顯示（`_update_scrollbar_visibility()`），內容變矮時會自動 `pack_forget()`。
- 主要內容區以 `columns_frame` 用 `grid` 分成 `left_col`/`right_col` 兩欄；`_apply_responsive_layout(width)` 依視窗寬度是否超過 `WIDE_LAYOUT_BREAKPOINT`（1000px）決定兩欄要左右並排（`grid(row=0, column=0/1, ...)`）還是上下堆疊（`columnspan=2`），寬窄狀態改變時才會重新 `grid`，避免不必要的重排。
- 路線座標點表格另外包了一層獨立的 `route_canvas`（`_update_route_table_height()`），最多顯示 `ROUTE_TABLE_MAX_ROWS`（15）列，超過才出現自己的捲軸，邏輯與外層視窗捲動並行但各自獨立管理捲軸顯示/隱藏。
- 滑鼠滾輪事件是全域綁定（`canvas.bind_all("<MouseWheel>")`），`_on_mousewheel` 內會判斷游標是否位於 `route_container` 之下，藉此決定要捲動外層視窗還是路線表格內層的 `route_canvas`。

### UI 結構
- 全部手刻 `tkinter`/`ttk`（無第三方 UI 框架），顏色一律讀取上述「主題系統」的模組全域變數，不要在 widget 裡寫死色碼。
- `_build_ui()` 一次性建構所有面板；模式切換靠 `_switch_mode()` 用 `pack()`/`pack_forget()` 顯示或隱藏對應的 Frame（`pin_frame`、`speed_frame_ref`、`route_section` 等），而不是建立多個視窗或使用 `Notebook`。切主題（見上）會整個銷毀重建 `_build_ui()`，因此 `_build_ui()` 內不應假設只會被呼叫一次。
- 路線點表格（`route_container`）是動態產生的：每次新增/刪除點都呼叫 `_refresh_route_rows()` 整個重建所有列，而不是局部更新。
