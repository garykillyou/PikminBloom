# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 專案概述

單一檔案 Python/CustomTkinter 桌面工具，透過 `pymobiledevice3` 模擬 iPhone（iOS 26）的 GPS 定位，
免越獄、免 iTunes，僅需 USB 連線。整個應用程式邏輯都在 [gps_app.py](gps_app.py) 一個檔案中，
沒有其他模組、套件或子目錄。執行期間會在同目錄產生兩個 JSON 狀態檔：`gps_favorites.json`
（最愛地點/路線）與 `gps_settings.json`（主題偏好與視窗幾何）。

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
- 背景執行緒中若要更新 UI（進度條、日誌、按鈕狀態），一律要透過 `self.after(0, ...)` 排回主執行緒，不可直接操作 widget。更新進度文字要呼叫 `_set_progress_label(text)`：`CTkLabel` 沒有 `tk.Label` 的 `config(**dict)` 用法，不能像舊版那樣在 `after()` 裡塞 dict。
- 四顆控制按鈕（開始/返回/停止/恢復真實定位）的狀態統一由 `_sync_btn_states()` 依 `self.pending_action` 與 `self.mode` 推導，不再各自散落 `config(state=...)`；`_on_paused()`（暫停/返回中斷後）與 `_on_session_ended()`（`_run_session()` 的 `finally` 區塊，連線真正結束後）兩個 callback 都只是呼叫它，`_update_return_btn_state()` 另外控制「返回」按鈕只在路線模式且未在返回/斷線中時可用。`_build_ui()` 尾端也會呼叫 `_sync_btn_states()`，所以切換主題整個重建 UI 之後狀態不會退回預設值。
- 實際切換單一按鈕要走 `_set_btn_enabled(btn, enabled)`，不要直接 `configure(state=...)`：`CTkButton` 的 `state="disabled"` 只會把文字換成 `text_color_disabled`、背景色完全不動（`ctk_button.py` 的 `_draw()` 只改 `_text_label` 的 `fg`），會讓停用中的「停止」仍是滿版 `DANGER` 底而看起來比可按的按鈕更醒目。每顆按鈕「啟用時」的顏色在 `_build_ui()` 建立後登記在 `btn.enabled_bg` / `btn.enabled_fg`，停用時一律換成 `DISABLED_BG` + `DISABLED_TEXT`，並同時 `hover=False` 關掉滑入效果。
- 新增/修改任何動作（`pending_action` 的新值）時，需同步確認：(a) `_session_main()` 的 if/elif 分派邏輯、(b) 對應的 `_walk_*()` 協程如何在動作被外部改變時中斷並保留 `self.point_idx`、(c) 觸發該動作的按鈕要如何重置其他按鈕狀態。

### 最愛地點（Favorites）
- 列表的欄寬由 `FAV_ROW_H` / `FAV_COL_ICON_W` / `FAV_COL_NAME_MIN_W` / `FAV_COL_PREVIEW_W` / `FAV_COL_DEL_W` 固定，只有名稱欄吃剩餘寬度。**每一列的右側欄位（✕、載入、座標預覽）一定要先 `pack(side="right")`**，因為 pack 是先到先分配空間；先放右側欄位，名稱再長也只能吃剩下的。
- 名稱與座標預覽都包在 `_fixed_cell()`（`pack_propagate(False)` 的容器）裡。`CTkLabel` 會依文字長度自動撐寬，不包容器的話過長的名稱會把同一列其他欄位擠變形。
- 名稱過長時由 `_bind_elide()` 綁在欄位容器的 `<Configure>` 上自動截斷並補「…」（`elide_to_width()` 二分搜尋算可容納的前綴）。綁在容器而不是建立時算一次，是因為名稱欄寬度會隨視窗寬度改變。
- 儲存在執行檔同目錄的 `gps_favorites.json`（`FAVORITES_FILE`），由 `load_favorites()` / `save_favorites()` 讀寫，內容是 list of dict，`type` 欄位為 `"pin"` 或 `"route"`。
- UI 清單（`_refresh_fav_list`）與載入邏輯（`_load_fav`）都靠這個 `type` 欄位分派要切到哪個模式、要填哪些欄位；新增最愛欄位時要同步確認存檔格式與讀取端都對得起來。
- 路線最愛除了手動輸入座標（`_save_current_route_as_fav`）外，也可從 KML 檔案匯入（`_import_kml_as_fav` → `parse_kml_route()`）：解析第一條 `LineString` 作為路線座標，並用起訖點附近（約 50 公尺內）的 `Point` 名稱自動當作起訖點備註，其餘中間點備註留空。

### 主題系統（深色 / 淺色）
- 兩組色票集中定義在檔案開頭的 `THEMES` dict（`"dark"` / `"light"`），`_pair(key)` 把同名色票組成 CustomTkinter 的 **`(淺色, 深色)` tuple**，再指派給模組層級常數（`BG`/`BG2`/`BG3`/`HOVER`/`ACCENT`/`ACCENT2`/`DANGER`/`TEXT`/`TEXT2`/`TEXT_ON_ACCENT`/`TEXT_ON_ACCENT2`/`DISABLED_BG`/`DISABLED_TEXT`）。tuple 順序固定是 `(light, dark)`，對調會讓兩個主題的顏色互換（CTk 內部是 `color[appearance_mode]`，light=0、dark=1）。
- `TEXT_ON_ACCENT` 專用於亮底色（`ACCENT`/`DANGER`）、`TEXT_ON_ACCENT2` 專用於暗底色（`ACCENT2`/`HOVER`），兩者不可互換；`DISABLED_BG`/`DISABLED_TEXT` 專供按鈕停用狀態（亮度刻意壓在 `BG3` 之下，讓停用按鈕退到「可按的次要按鈕」之後）。
- **所有 widget 的顏色參數一律傳這些 tuple 常數，不要傳單一色碼字串**——傳字串的 widget 在切換主題時不會跟著換色，會變成畫面上唯一殘留舊主題的元件。
- 按鈕配色已收斂成四組 dict：`BTN_PRIMARY` / `BTN_SECONDARY` / `BTN_SUCCESS` / `BTN_STOP`，用 `**BTN_PRIMARY` 展開。**`hover_color` 一定要明確給值**：`CTkButton` 沒指定時會套用 CustomTkinter 預設主題（藍色系）的 hover 色，與本 App 色票完全不搭。
- 目前套用的主題名稱存在 `self.theme_name`，並持久化在 `gps_settings.json`（`load_settings()` / `save_settings()`）；啟動時讀取上次的偏好，找不到或值不合法就 fallback 回 `"dark"`。`ctk.set_appearance_mode()` 必須在 `super().__init__()` **之前**呼叫，因為 `CTk.__init__()` 會依當下模式決定 Windows 標題列要用深色還是淺色。
- `_toggle_theme()` 只做三件事：翻轉 `self.theme_name`、呼叫 `ctk.set_appearance_mode()`、存檔。CustomTkinter 會自己把每個已建立的 widget 重畫成另一組色，**不需要銷毀重建 UI**，也因此不必暫存/還原使用者正在輸入的欄位。新增欄位時不用再擔心切主題會遺失輸入。

### 視窗位置記憶（多螢幕）
- 視窗大小/座標/是否最大化存在 `gps_settings.json` 的 `"window"` 欄位，由 `_restore_window_geometry()`（啟動時還原）、`_remember_window_geometry()`（`<Configure>` 事件持續記錄）、`_save_window_geometry()`（寫檔；由 `_on_close()` 經 `protocol("WM_DELETE_WINDOW", ...)` 觸發，`_toggle_theme()` 也改呼叫它而非直接 `save_settings()`，否則切主題會把啟動時讀進來的舊 `window` 值再寫一次）三個方法負責；沒有設定檔時 fallback 回 `DEFAULT_WINDOW_W/H`（1500x820）+ 最大化，也就是舊行為。
- 多螢幕之所以會回到上次那一台，是因為 `__init__` 先 `geometry(...+x+y)` 把視窗擺到上次的座標，`_settle_window_and_reset_scroll()` 才 `state("zoomed")`——Windows 的最大化是相對於視窗當下所在的螢幕，順序反了就一定回到主螢幕。
- `_remember_window_geometry()` 只在 `state() == "normal"` 時記座標（最大化時的 `-8, -8` 不能當還原基準），且一律解析 `self.geometry()` 字串而非 `winfo_x()/winfo_y()`：後者是客戶區座標，與 `geometry()` 設定用的外框座標差一個標題列高度，混用會讓視窗每次啟動往下漂移。另外根視窗的 bindtag 在所有子 widget 上都有，所以處理函式開頭必須用 `event.widget is not self` 擋掉子 widget 的 `<Configure>`。
- 螢幕被拔掉或解析度改變時，舊座標會讓視窗跑到看不見的地方。`winfo_screenwidth()` 只回報主螢幕大小不足以判斷，因此改用 `point_on_any_monitor()`（ctypes 呼叫 Win32 `MonitorFromPoint` + `MONITOR_DEFAULTTONULL`，拿標題列中心點去問）；驗證失敗就只套用大小、位置交給 Windows 決定。非 Windows 平台一律視為有效。
- **DPI 換算**：CustomTkinter 會呼叫 `SetProcessDpiAwareness()`，之後 `CTk.geometry()` 取得/設定的都是「邏輯像素」（設值走 `_apply_geometry_scaling`、取值走 `_reverse_geometry_scaling`，兩邊自洽），但 `MonitorFromPoint` 吃的是**實體像素**。因此傳進 `point_on_any_monitor()` 之前一定要先過 `_logical_to_physical()`（用 `ctk.ScalingTracker.get_window_scaling(self)` 換算）。螢幕縮放 100% 時係數為 1，兩者相同；在 125%/150% 的螢幕上不換算就會誤判「座標不在任何螢幕上」而放棄還原位置。
- `self.bind("<Configure>", ...)` **必須加 `add="+"`**：`CTk.__init__()` 自己也綁了 `<Configure>`（`_update_dimensions_event`）來追蹤視窗尺寸，不加就會把它蓋掉。

### 視窗捲動與響應式版面
- 整個視窗內容包在 `CTkScrollableFrame`（`_build_scroll_container()` 建立 `self.container` → `self.scroll_frame`）。CustomTkinter 已內建 Canvas、捲軸與滾輪事件，舊版那一整套手刻 Canvas 管線（`_content_fits` / `_scroll_canvas` / `_widget_is_descendant` / `_on_mousewheel`）已全部移除。
- 捲軸「內容塞得下就隱藏」不是 CTk 內建行為（`CTkScrollableFrame._create_grid()` 是無條件 `grid()` 捲軸的），由模組層級的 `set_scrollbar_visibility()` 自行處理。**這個函式刻意存取 `_scrollbar` / `_parent_canvas` 兩個私有屬性**，是與 CustomTkinter 內部實作耦合的已知風險點；已用 `getattr` + `try` 包住，未來版本改名時只會退回「捲軸固定顯示」而不會讓 UI 壞掉。升級 customtkinter 後請優先驗證這裡。
- 主要內容區以 `columns_frame` 用 `grid` 分成 `left_col`/`right_col` 兩欄；`_apply_responsive_layout(width)` 依視窗寬度是否超過 `WIDE_LAYOUT_BREAKPOINT`（1000px）決定兩欄要左右並排（`grid(row=0, column=0/1, ...)`）還是上下堆疊（`columnspan=2`），寬窄狀態改變時才會重新 `grid`，避免不必要的重排。觸發來源是 `self.container` 的 `<Configure>`（`_on_container_configure`）。
- 路線座標點表格是**內層的另一個 `CTkScrollableFrame`**（`self.route_container`），`_update_route_table_height()` 依列高把它的 `height`（可視高度）設成最多 `ROUTE_TABLE_MAX_ROWS`（15）列。巢狀捲動不需要手動分派事件：CTk 的 `_check_if_valid_scroll()` 會沿 `master` 往上走並比對 `_parent_canvas`，游標在內層表格上時外層不會跟著捲。
- 注意 `route_container.winfo_height()` 回傳的是**內容總高度**（CTkScrollableFrame 自己就是那個內容 frame），不是可視高度；可視高度在它的 `_parent_canvas` 上。

### 路線表格：虛擬化清單
一次只看得到 15 列，所以**不論路線有幾個點都只建立 `ROUTE_ROW_POOL`（17）個列 widget**，捲動時把它們重新綁到不同的資料索引。這是效能必要措施而非優化：一個 CTk widget 約 3ms，446 個點若每列都建就是 2230 個 widget、載入要 8 秒；虛擬化後固定 0.3 秒，且與路線長度無關（5000 點也一樣）。

要改這塊時必須同時顧到：
- **列是用 `place()` 疊上去的**，`place` 不會把容器撐高，所以靠 `self._route_spacer`（高度 = 總列數 × 列高）決定捲動範圍。新增/刪除點後要更新墊片高度（`_refresh_route_rows()` 負責）。
- **`CTkBaseClass.place()` 禁止傳 `width`/`height`**（那是建構子的參數，CTk 要自己套縮放）。不傳的話 place 會用列的自然高度，剛好就是 `_route_row_height()` 量到的值。
- **`place()` 的座標是實體像素**，而 `configure(height=...)` 是 widget 單位，兩者不可混用（見 `_physical_to_widget_units()`）。
- **換綁資料時 `var.set()` 會觸發 Entry 的 write callback**，必須用 `self._route_rebinding` 擋掉，否則會把上一列的值寫進新綁上來的那一筆資料。這是最容易寫錯、而且症狀是「資料默默被改掉」的地方，改動後務必測「反覆捲動後 route 內容不變」。
- 列上的刪除鈕與編輯 callback 都改成吃 `row.data_index`（目前綁哪一筆）而不是建立時的固定索引；沒綁資料的列 `data_index` 是 `None`。
- 捲動事件靠 `_install_route_scroll_hook()` 包住內層 canvas 的 `yscrollcommand`（CTkScrollableFrame 沒有對外的捲動事件），與 `set_scrollbar_visibility()` 同屬與 CustomTkinter 內部耦合的點。
- 表格欄寬用 `ROUTE_COL_INDEX_W` / `ROUTE_COL_COORD_W` / `ROUTE_COL_DEL_W` 三個像素常數，表頭與資料列共用。注意 `CTkLabel`/`CTkEntry` 的 `width` 是**像素**而非 tkinter 的字元數，改欄寬要兩邊一起改才不會錯位。

### UI 結構
- UI 全部用 **CustomTkinter**（`import customtkinter as ctk`）。`tkinter` 只剩下三個用途：`StringVar`/`DoubleVar`/`BooleanVar`，以及 `messagebox`/`simpledialog`/`filedialog` 對話框（CTk 沒有等價物，外觀會是系統原生樣式，與 CTk 風格略有落差，屬已知取捨）。
- 顏色一律用「主題系統」的 tuple 常數，不要在 widget 裡寫死色碼。
- 字級一律用 `FS_XS`/`FS_SM`/`FS_MD`/`FS_LG`/`FS_XL`/`FS_TITLE`/`FS_EMOJI`/`FS_EMOJI_LG` 常數，**不要在 widget 裡直接寫數字**。下限刻意訂在 `FS_XS = 10`pt：中文字在 11px 以下筆畫會糊在一起，舊版沿用的 8pt/9pt 對拉丁字母還能看，中文則完全不行。
- `UI_SCALE`（目前 1.15）透過 `ctk.set_widget_scaling()` 整體再縮放字級與 widget 尺寸，是「整份 UI 一起變大變小」的單一調節點；它只影響 widget，不影響視窗幾何（那是 window scaling）。
- 因為有 widget scaling，**`winfo_reqheight()` / `<Configure>` 的 `event.height` 拿到的是縮放後的實際像素，不能直接餵回 `configure(height=...)`**（CTk 會再乘一次 scaling）。要先過 `_physical_to_widget_units()`，`_update_log_height()` 與 `_update_route_table_height()` 都是這樣處理的。
- 執行日誌高度 = 視窗高度 40% 再扣掉 `LOG_SHRINK_LINES`（3）行，行高由 `_log_line_height()` 用未縮放字級向 Tk 問出來並快取。要調日誌高低改這個常數即可。
- `CTkFrame` 沒有 `tk.Frame` 的 `padx`/`pady` 內距參數，卡片式面板一律用 `make_card(parent, padx, pady)` 建立，它回傳 `(外框, 內容框)`：**外框**負責 `pack()`/`pack_forget()`（模式切換用），子 widget 一律放進**內容框**。
- `CTkButton` 的 `padx`/`pady` 同樣不存在，文字左右內距改用 `border_spacing`；按鈕會依文字自動撐寬（內部 `tkinter.Frame` 沒有關掉 geometry propagation），所以小按鈕一律傳 `width=1` 讓文字決定寬度，只用 `height` 控制高度。
- `_build_ui()` 一次性建構所有面板；模式切換靠 `_switch_mode()` 用 `pack()`/`pack_forget()` 顯示或隱藏對應的 Frame（`pin_frame`、`speed_frame_ref`、`route_section` 等），而不是建立多個視窗或使用 `Notebook`。切主題不再重建 UI，因此 `_build_ui()` 在一次執行中只會被呼叫一次。
- 路線點表格是**虛擬化清單**，詳見下節。
- `CTkProgressBar` 的值域是 **0~1**（不是百分比），`self.progress_var` 存的一律是小數；進度文字標籤才顯示 `frac*100`。
- `CTkEntry` 不支援 `insertbackground`，游標顏色無法自訂（遷移時放棄的功能）。
