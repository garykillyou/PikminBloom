# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 專案概述

Python 桌面工具，透過 `pymobiledevice3` 模擬 iPhone（iOS 26）的 GPS 定位，免越獄、免 iTunes，
僅需 USB 連線。GUI 用 **PySide6 + qasync + qt-material**（[gps_qt/](gps_qt) 套件），進入點為
`gps_qt/main.py`。

座標可以直接在內嵌的 Leaflet 地圖上點選、拖曳、刪除（[gps_qt/web/](gps_qt/web)），
移動中還會即時畫出目前位置與已走軌跡。

狀態存在專案根目錄下的兩個 JSON 檔（皆已列入 `.gitignore`）：
- `gps_favorites.json`：最愛地點／路線（`{"type": "pin"|"route", "name", ...}` 陣列）。
- `gps_settings.json`：`theme`（主題偏好）、`window`（視窗幾何 + `maximized`）、
  `last_route`（上次的路線座標點）、`speed_kmh`（上次的移動速度）、
  `map`（地圖的 `tile_source`／`custom_tile_url`／`custom_attribution`／`center`／`zoom`／`follow`／
  `routing_costing`／`simplify_m`，由 `persistence.load_map_settings()` 補齊預設值）。

## 常用指令

```bash
# 安裝相依套件
pip install -r requirements.txt

# 執行 App（tunneld 需已啟動）
python -m gps_qt.main

# 手動啟動 tunneld（需「系統管理員」終端機，建立 iOS 26 的 RemoteXPC 加密通道）
python -m pymobiledevice3 remote tunneld

# 執行測試（只涵蓋純邏輯：geo、map_bridge payload、geocode 解析、設定正規化）
pip install -r requirements-dev.txt
python -m pytest
```

一般情況下不需要手動跑 tunneld：雙擊 [run.bat](run.bat) 會先呼叫
[start_tunneld.ps1](start_tunneld.ps1) 偵測 `127.0.0.1:49151` 是否已經有人在聽，沒有的話用
`Start-Process -Verb RunAs` 以系統管理員身分啟動 tunneld（會跳 UAC），等幾秒後再用 `pythonw`
啟動 App（不顯示主控台視窗，cmd 視窗隨即關閉）。`start_tunneld.ps1` 用離開碼傳遞狀態：
`0` = tunneld 已在執行、`1` = 剛啟動（run.bat 據此決定要不要等待）。

測試只涵蓋不需要 Qt 事件迴圈的純函式（[tests/](tests)），Widget 與地圖頁面沒有自動化測試；
專案沒有 lint 或 build 設定，也沒有 CI。

## 架構重點

### 檔案地圖
```
PikminBloom/
├── run.bat              # 啟動捷徑：先確保 tunneld 在跑，再用 pythonw 開 App
├── start_tunneld.ps1    # 偵測 49151 埠，必要時以系統管理員啟動 tunneld
├── conftest.py          # 讓 pytest 把根目錄加進 sys.path
├── tests/               # 純函式測試（不需要 Qt 事件迴圈）
└── gps_qt/
    ├── main.py              # 進入點：QApplication + qasync 事件迴圈
    ├── theme.py             # qt-material 主題套用、字級覆寫、danger/success 語意色
    ├── geo.py               # haversine()、interpolate_points()、douglas_peucker()
    ├── persistence.py       # JSON 存讀 + KML 解析 + 地圖設定正規化
    ├── window_geometry.py   # 視窗位置記憶（QScreen API）
    ├── session.py           # GPSSession：連線狀態機（pending_action 設計）
    ├── models.py            # RouteTableModel + DeleteButtonDelegate（路線表格虛擬化）
    ├── map_bridge.py        # QWebChannel 契約（MapBridge）+ payload 序列化純函式
    ├── geocode.py           # Nominatim 地名搜尋（Python 端發送，符合使用政策）
    ├── routing.py           # Valhalla 路徑規劃 + polyline6 解碼
    ├── web/                 # 地圖頁面（QWebEngineView 以 file:// 載入）
    │   ├── map.html / map.css / map.js
    │   └── vendor/          # Leaflet 1.9.4 本地副本（不依賴 CDN）
    └── widgets/
        ├── main_window.py      # 整體版面、控制按鈕狀態機、模式切換、地圖連動
        ├── map_panel.py        # QWebEngineView + Qt 原生工具列（搜尋/圖磚/跟隨/清軌跡）
        ├── route_planner.py    # 路徑規劃工具列：點起訖點 → 算出沿道路的路線
        ├── pin_panel.py        # 固定定位模式面板（含座標貼上攔截）
        ├── route_panel.py      # 路線模式面板（速度設定 + 路線表格）
        └── favorites_panel.py  # 最愛清單
```

### 執行流程（連接 iPhone 的關鍵鏈路，長連線架構）
1. `tunneld` 必須以系統管理員權限先啟動（`run.bat` 會自動處理，或手動跑
   `python -m pymobiledevice3 remote tunneld`），建立 iOS 26 的 RemoteXPC 通道。
2. 按「開始模擬」時，[session.py](gps_qt/session.py) 的 `GPSSession._session_main()` 用 `asyncio.ensure_future()` 建立一個常駐 task，`async with DvtProvider(rsd) as dvt, LocationSimulation(dvt) as sim:` 開一次連線後就常駐在 while 迴圈裡；後續按「停止」「往起點／往終點」都**不會**重建 task 或重新連線，只是改變 `self.pending_action` 這個共享狀態（`"forward" | "reverse" | "pause" | "disconnect"`），由 while 迴圈讀取並分派動作。
3. 直到 `pending_action == "disconnect"`（使用者按「恢復真實定位」）才 `break` 出迴圈、呼叫 `sim.clear()` 並讓 `async with` 關閉連線——恢復真實 GPS 只會在明確斷線時發生，單純停止／切換方向都仍保持模擬連線在目前座標。
4. 座標注入本身是 `sim.set(lat, lon)`，呼叫位置在 `_walk_route()` / `_walk_pin()` 這兩個由 `_session_main()` 依 `pending_action` 呼叫的協程裡。

### 兩種模式（由 `MainWindow.mode` 控制，動作由 `pending_action` 驅動）
- **路線模式（route）**：`_walk_route(sim, direction)` 中 `direction=1` 往終點走、`direction=-1` 往起點走回去。
  `GPSSession.reverse()`（由「往起點／往終點」按鈕觸發）是**方向切換**而非一次性動作：目前不是
  `"reverse"` 就切成 `"reverse"`，已經是就切回 `"forward"`，所以走回去的途中可以再按一次改回前進。
  `interpolate_points()` 依 `haversine()` 算出的距離與設定速度（UI 以 km/h 輸入，經 `speed_ms()` 換算成 m/s）把路線切成每秒一個內插點；目前走到第幾個內插點記錄在 `point_idx`，中斷（停止／切換方向／斷線）時會停在原點，之後從該點繼續。
  循環模式（來回往復）不是在進入 `_walk_route()` 時快取的：**每次抵達端點才即時讀取** `loop_provider()`，
  因此使用者中途勾選／取消勾選會在下一次抵達端點時生效；折返時會一併更新 `direction`、`action_name`
  與 `pending_action`，並 emit `direction_changed`，讓按鈕文字跟著改成新的方向。
- **固定定位模式（pin）**：`_walk_pin(sim)` 呼叫一次 `sim.set(lat, lon)` 後立刻把 `pending_action` 設回 `"pause"`，讓外層 while 迴圈進入 `await asyncio.sleep(0.2)` 的閒置分支，藉此在同一條長連線上「保持」定位，直到使用者按「停止」（其實已經是 pause 狀態，UI 只更新按鈕）或「恢復真實定位」。

### 地圖面板：QWebEngineView + Leaflet + QWebChannel
右欄以地圖為主體（[map_panel.py](gps_qt/widgets/map_panel.py)），座標面板在下方可整個收合。

**溝通契約**全部走 [map_bridge.py](gps_qt/map_bridge.py) 的 `MapBridge`：signal 是 Python → JS
（JS 端 `bridge.xxx.connect()`），slot 一律命名為 `on_*` 是 JS → Python（slot 收到後轉成去掉
`on_` 前綴的同名 Qt signal，讓 `MapPanel` 用一般的 `.connect()` 接）。新增任何互動時兩邊都要成對加。

- **回授迴圈防護（最容易踩的坑）**：模型變動會回推整條路線給地圖，而地圖拖曳又會回寫模型。
  兩層擋住：(a) `MapPanel._schedule_route_push()` 用 `QTimer.singleShot(0)` 把同一輪事件迴圈的
  多次推送合併成一次；(b) `map.js` 的 `renderRoute()` 比對「JSON 與上次收到的完全相同就跳過重繪」。
  因此 **`route_payload()` 絕對不能加流水號、時間戳這類每次都會變的欄位**，加了 (b) 就失效。
  另外節點拖曳只在 `dragend` 通知 Python（`drag` 過程僅在本地更新折線），確保回推一定發生在
  拖曳結束後，不會把正在拖的 marker 重建掉。
- **頁面是非同步載入的**：`MapPanel` 的每一項狀態都先存成成員變數，等頁面回報 `map_ready`
  才在 `_on_map_ready()` 一次推過去（順序有意義：先視野與圖磚，再畫內容，最後才套鎖定狀態——
  鎖定會重畫所有節點圖示，必須在節點已存在之後）。之後的變動才即時送出。
- **三個查證過的載入陷阱**：
  1. `main.py` 必須在建立 `QApplication` **之前** `import PySide6.QtWebEngineWidgets`，Qt 6 要在
     那時候設好 `AA_ShareOpenGLContexts`，順序反了會直接中止。那行 import 看起來沒用到但不能刪。
  2. `qwebchannel.js` 不從 CDN 抓，也不能用 `qrc:///qtwebchannel/qwebchannel.js`（`file://` 頁面
     讀不到 qrc）；改成 `QFile(":/qtwebchannel/qwebchannel.js")` 讀出原始碼，用 `QWebEngineScript`
     在 `DocumentCreation` 時機注入，`map.js` 執行時 `QWebChannel` 才一定已存在。
  3. `map.html` 是 `file://` 頁面而圖磚來自 https，必須打開
     `QWebEngineSettings.LocalContentCanAccessRemoteUrls`，否則圖磚全被擋掉而且**沒有任何錯誤訊息**。
- **工具列刻意做在 Qt 這一側**而不是 HTML 裡，這樣搜尋框/下拉選單/核取方塊直接吃 qt-material
  的樣式，不必在 `map.css` 裡再複製一套跟著主題切換的控制項樣式。
- **編輯鎖**：`_sync_btn_states()` 在 `pending_action` 為 `forward`/`reverse` 時送 `edit_locked(True)`。
  固定定位「保持中」（`_walk_pin()` 注入完已把 `pending_action` 設回 `pause`）**不算移動中**，
  此時在地圖上點新座標會由 `_reinject_pin_if_holding()` 立刻重新注入一次，人就直接搬過去。
- **軌跡**：`session.position_changed` 每次 `sim.set()` 後 emit，`map.js` 用 `polyline.addLatLng()`
  累加；超過 `TRAIL_MAX_POINTS`(3000) 就每兩點抽一點，循環模式跑整夜也不會累積出巨大的 polyline。
- **跟隨**：使用者手動拖動地圖（`dragstart`）會自動關閉跟隨並回報 Python 同步核取方塊；
  `panTo()` 不觸發 `dragstart`，所以程式自己的平移不會誤關。
- **圖磚**：`TILE_SOURCES` 內建 OSM／CartoDB Positron／Dark Matter／自訂 URL，預設 `"auto"`
  跟著主題換（深色配 Dark Matter、淺色配 Positron）；使用者手動選過就固定下來不再跟著主題跑。
  Leaflet 原生支援 `{s}`／`{r}`，不需要自己展開。**這些公用圖磚僅供輕量使用且必須保留 attribution。**
- **地名搜尋刻意由 Python 端發送**（[geocode.py](gps_qt/geocode.py) 用 `QNetworkAccessManager`）：
  Nominatim 政策要求可識別的 User-Agent 且每秒最多 1 次，在 QWebEngine 裡 `fetch()` 帶的是瀏覽器
  UA，改不掉也不合規。route 模式搜尋只帶視野過去，**不自動加點**。
- **Leaflet 本地化**在 `web/vendor/`：純靠 CDN 時斷網會整頁白，本地化後控制項仍在，
  只有圖磚空白並由 `tileerror` 顯示提示橫幅。

### 路徑規劃：Valhalla + Douglas-Peucker
`interpolate_points()` 在兩點之間走的是**直線**；要沿實際道路走就必須有路網資料，
這由 [routing.py](gps_qt/routing.py)（查詢）與 [route_planner.py](gps_qt/widgets/route_planner.py)（互動）負責。

- **服務是 Valhalla 的 FOSSGIS 公用實例**，不需要 API 金鑰，支援 `pedestrian`／`bicycle`／`auto`
  三種 costing。**這是社群維運的免費服務，政策是「合理使用」**，不要拿來做批次查詢。
- **`shape` 是精度 1e6 的 polyline**（一般的 Google polyline 是 1e5）。用錯精度不會報錯，
  只會讓座標差十倍，所以 `POLYLINE_PRECISION` 寫成具名常數，並有一個測試專門釘住這件事。
- **多個 leg 的接縫點會重複**（前一段的終點等於下一段的起點），`parse_route()` 會去掉重複的
  那一個，否則路線裡會出現距離為零的相鄰點。
- **回傳的轉彎點動輒上百上千個**（實測台中火車站→台灣大道三段 3.3 公里有 132 點），直接塞進
  座標表格會難以手動微調，所以用 `geo.douglas_peucker()` 抽稀，預設容差 5 公尺（實測降到 22 點，
  路形肉眼看不出差別）。`douglas_peucker()` **刻意用顯式堆疊而非遞迴**：遞迴版深度最壞等於點數，
  上千點會撞到 Python 的遞迴上限。
- **點選狀態機在 `RoutePlanner`**（IDLE → PICKING_START → PICKING_END → ROUTING），刻意不放在
  `MapPanel` 裡：後者的職責是「顯示地圖並轉發互動」，混進來會讓它膨脹到不好讀。`MapPanel._on_map_clicked()`
  一律先問過 `route_planner.handle_map_click()`，**被吃掉就不能再當成新增座標點**——新增任何
  「會攔截地圖點擊」的功能都要沿用這個「攔截成功才吃掉事件」的形狀。
- 切到固定定位模式或模擬開始移動（編輯鎖）時都要呼叫 `route_planner.cancel()`，否則按鈕會卡在
  「請點選終點」卻永遠等不到點擊。

### 非同步整合：qasync
[main.py](gps_qt/main.py) 用 `qasync.QEventLoop` 包住 `QApplication` 並 `asyncio.set_event_loop(loop)`，讓 asyncio
事件迴圈直接跑在 Qt 事件迴圈的同一條 thread 上，因此 `GPSSession._session_main()`／`_walk_route()`／
`_walk_pin()` 可以直接是 async 方法，不需要背景 thread、也不需要跨執行緒 marshalling。`GPSSession` 用
Qt signal（`log`/`progress_value`/`progress_label`/`paused`/`session_ended`/`direction_changed`）把狀態
送出，`MainWindow.__init__` 用 `.connect()` 接對應的 slot。

新增/修改任何動作（`pending_action` 的新值）時，需同步確認：(a) `_session_main()` 的 if/elif 分派邏輯、
(b) 對應的 `_walk_*()` 如何在動作被外部改變時中斷並保留 `point_idx`、(c) 觸發該動作的按鈕要如何在
`MainWindow._sync_btn_states()` 重置其他按鈕狀態。

### 控制按鈕狀態機（`MainWindow._sync_btn_states()`）
- `busy`（`pending_action` 為 `forward`/`reverse`/`disconnect`）時停用「開始模擬」與「恢復真實定位」。
- `holding`（已連線且 `pending_action == "pause"`）時「停止」仍要可按——固定定位模式啟動後會立刻回到
  `"pause"`，此時連線還在，若停用「停止」會跟 `_walk_pin()` 印出的提示訊息互相矛盾。
- 「恢復真實定位」在 `session_active` 為 False 時（從未連線或已斷線）停用；移動中按下會先跳警告要求
  使用者先按「停止」。
- `_update_return_btn_state()` 判斷「已啟動」是看 `pending_action` 是否已經是 `forward`/`reverse`，
  **不是**只看 `session_active`——後者要等背景協程真的連上裝置才會變 True，且沒有訊號通知 UI。
  按鈕文字顯示「按下去會往哪裡走」：目前是 `"reverse"` 就顯示「往終點」，否則顯示「往起點」。
- 連線結束（正常斷線或出錯）時 `_on_session_ended()` 會先把 `pending_action` 歸零成 `"pause"` 再同步
  按鈕，否則殘留的 `"disconnect"` 會讓按鈕全部卡在停用。

### 主題系統：qt-material，一個重要陷阱
- [theme.py](gps_qt/theme.py) 的 `apply()` 呼叫 `qt_material.apply_stylesheet(app, theme=..., invert_secondary=...)`
  套用內建的 `dark_red.xml` / `light_red.xml`（qt-material 目前只用內建色票，沒有覆寫成自訂品牌色，
  這是使用者明確要求）。淺色主題要傳 `invert_secondary=True`，否則 qt-material 的 `secondaryColor`
  系列預設是深色系（給深色主題用），淺色主題文字對比會不足。
- **陷阱**：qt-material 的樣式表最上層有 `* { font-size: ...px; ... }`，套用在 `QApplication` 層級後會
  蓋掉個別 widget 用 `setFont()` 設定的字級（Qt 樣式表屬性一旦命中該 widget，優先權高於程式設定的
  `QFont`——已用 `QFontInfo` 實測驗證過）。所以任何字級例外（區塊標題、App 標題）都不能只呼叫
  `setFont()`，要用 `mark_class(widget, "app-title"/"section-title")` 設定 Qt 動態屬性 `class`，並在
  `EXTRA_QSS_TEMPLATE` 補一段對應的 `.app-title`/`.section-title` 選擇器（`apply()` 產生完 qt-material
  的樣式表後會再 append 這段），才蓋得過去。新增任何「這個 widget 字級要特別大/特別色」的需求都要走
  這個模式，不要直接 `setFont()`。
- 按鈕的語意色（危險/成功動作）也是同一套機制：`mark_class(btn, "danger")`／`mark_class(btn, "success")`
  對應 qt-material 內建的 `QPushButton.danger`／`.success` 規則（靠 Qt 動態屬性 `class` 選取，這點已用
  offscreen 平台實際渲染截圖驗證過，不是靠猜的）。`mark_class()` 呼叫完一定要 `unpolish()`/`polish()`
  才會重新計算樣式。
- **下拉選單會截字的陷阱**：qt-material 的 `QComboBox::drop-down { width: 20px }` 與
  `QComboBox::down-arrow { margin-right: 8px }` 畫在文字區右側，但 `QComboBox` 只有
  `padding-left`、沒有對應的右側 padding，`sizeHint()` 也沒把這塊完整計入；再加上
  `QComboBox` 預設的 `AdjustToContentsOnFirstShow` 只在第一次顯示時算一次寬度就鎖死
  （而 `MainWindow` 在 `_build_ui()` 之後還會再套用一次主題，路徑規劃列又是切到路線模式
  才顯示），選項文字一長就會被箭頭壓掉一截。**所有 `QComboBox` 一律要過一次
  `theme.fit_combo_width()`**（設 `AdjustToContents` + 補 `COMBO_ARROW_ALLOWANCE`），
  不要自己 `setMinimumWidth()` 寫死像素。與 `_fix_to_hint()` 同樣必須在 `theme.apply()` 之後呼叫。
- 同一套機制還有一個 `.no-uppercase { text-transform: none; }`：qt-material 預設會把按鈕文字轉成大寫，
  速度預設按鈕（「步行 5 km/h」）這種含單位的文字被轉大寫後會變成「5 KM/H」，所以用
  `mark_class(btn, "no-uppercase")` 擋掉。
- 全域字體是 `Noto Sans TC`（比例字體，非等寬；使用者測試過多個等寬字體選項後決定用這個純粹當一般
  UI 字體）。要換字體只改 `apply()` 裡 `extra["font_family"]` 一處。
- 路線/固定定位模式切換按鈕是 `setCheckable(True)` + `QButtonGroup(exclusive=True)`，靠 qt-material
  內建的 `QPushButton:checked` 樣式顯示目前選取狀態，不需要手動切換顏色屬性。

### 視窗幾何：QScreen API
[window_geometry.py](gps_qt/window_geometry.py) 用 `QGuiApplication.screenAt(QPoint(x, y))` 判斷座標是否落在任何一台螢幕
內，回傳 `None` 就代表無效、位置交給 Windows 決定。Qt6 預設開啟 High-DPI scaling，`QWidget.geometry()`
拿到的座標本身就是邏輯像素，不需要手動做實體/邏輯像素換算。`MainWindow` 只在 `not self.isMaximized()`
時才更新 `_normal_geometry`（`resizeEvent`/`moveEvent` 都會呼叫），因為最大化時的幾何不能當還原基準；
`closeEvent()` 用這份記錄的座標存檔，同時把 `last_route` 與 `speed_kmh` 一起寫回 `gps_settings.json`。

### 路線表格：QTableView 虛擬化
[models.py](gps_qt/models.py) 的 `RouteTableModel(QAbstractTableModel)` + `RoutePanel`（[route_panel.py](gps_qt/widgets/route_panel.py)）
裡的 `QTableView` 原生只 render 可見列，不論路線有幾個點都不需要手動管理列 widget 的重複利用。
- 座標欄（緯度/經度/備註）靠 `Qt.ItemIsEditable` flag + `setData()` 支援直接編輯。
- 刪除欄用自訂的 `DeleteButtonDelegate(QStyledItemDelegate)`：`paint()` 畫文字、`editorEvent()` 攔截點擊
  發出 `delete_requested(row)` signal。**刻意不用 `setIndexWidget()`**——那會替每一列建立一個真正的
  `QWidget` 並常駐，等於又要自己管理 widget 生命週期，違背用 `QTableView` 換掉手刻虛擬化的目的。
- 刪除欄畫的是「刪除」二字（不用 icon/emoji），欄寬（`COL_DELETE`）要能容納文字，改文字時兩處要一起改。
- `_delete_point()` 在只剩 2 個點時直接 return：路線至少要兩點才能內插，UI 層先擋掉。
- `_update_info()` 由 `RouteTableModel` 的 `on_changed` callback 觸發，每次表格變動就重算總距離、依目前
  速度估算的預計時間與節點數，顯示在「路線座標點」標題右邊。

### 最愛清單：QListWidget + 自訂 eliding label
[favorites_panel.py](gps_qt/widgets/favorites_panel.py) 的 `FavoritesPanel` 項目數通常不多，不像路線表格要處理數千筆，
不需要虛擬化，直接用 `QListWidget` + `setItemWidget()` 掛自訂的列 widget。
- 名稱欄用 `_ElidingLabel(QLabel)`：`resizeEvent()` 裡用 `fontMetrics().elidedText()` 依目前寬度重新截斷
  加「…」，並設定 `QSizePolicy.Ignored` 讓它可以縮到比文字本身更窄。**這是修過的 bug**：一開始沒設
  `Ignored`，QLabel 的預設 `minimumSizeHint` 等於文字寬度，名稱一長就會把整列往右撐出可視範圍，必須
  橫向捲動才看得到後面的載入/編輯/刪除欄位；改用 `Ignored` + 動態截斷後，這幾個欄位永遠留在可視範圍
  內。
- 這幾個固定欄位（座標預覽、載入、編輯、刪除）的寬度用 `_fix_to_hint()` 依 widget 自己的 `sizeHint()`
  動態算出來，**不要**寫死像素常數：按鈕實際所需寬度取決於當下套用的 QSS padding，寫死的數字換主題或
  調字級後很容易太窄而裁切文字（也是修過的 bug）。呼叫時機必須在 `theme.apply()` 套用樣式表「之後」，
  `sizeHint()` 才會反映正確的 padding——`MainWindow.__init__` 因此把 `theme.apply()` 排在 `_build_ui()`
  之前呼叫。
- `refresh()` 同時做兩件事：依目前模式（pin/route）過濾清單內容，以及切換標題列按鈕的可見性——pin 模式
  只顯示「儲存目前座標」，route 模式只顯示「儲存目前路線」與「匯入 KML 路線」。切換模式時
  `MainWindow._switch_mode()` 會呼叫 `favorites_panel.refresh()`，兩者一起更新。
- 路線最愛除了手動輸入座標外，也可從 KML 檔案匯入（`_import_kml` → `persistence.parse_kml_route()`）：
  解析第一條 `LineString` 作為路線座標，並用起訖點附近（約 50 公尺內）的 `Point` 名稱自動當作起訖點
  備註，其餘中間點備註留空。

### 固定座標欄位：貼上「緯度, 經度」的攔截機制
[pin_panel.py](gps_qt/widgets/pin_panel.py) 的 `_CoordinatePasteLineEdit(QLineEdit)` 讓使用者把地圖複製來的
`24.981326, 121.451743` 直接貼進緯度或經度任一欄，就自動拆成兩個值分別帶入。
- **不能用 `insertFromMimeData()` 覆寫**：那是 `QTextEdit` 才有的掛勾，`QLineEdit` 沒有。
- **也不能覆寫 `paste()`**：右鍵選單的 Paste 動作在 C++ 端直接接到非 virtual 的 `paste()` slot，Python
  這邊的覆寫攔不到。
- 所以改為攔截兩個實際入口：`keyPressEvent()` 比對 `QKeySequence.StandardKey.Paste`（Ctrl+V），
  以及 `contextMenuEvent()` 裡把標準選單中 Paste 動作的 `triggered` 重接到自己的 handler。
- `_try_apply_pasted_coordinates()` 回傳 bool：字串不是「兩個以逗號分隔且都在合法經緯度範圍內的數字」
  就回 False，由呼叫端 fallback 回原本的貼上行為。新增類似的輸入攔截時要沿用這個「攔截成功才吃掉事件」
  的形狀，不要無條件吞掉貼上。

### 響應式版面
`MainWindow.resizeEvent()`（[main_window.py](gps_qt/widgets/main_window.py)）依視窗寬度是否超過 `WIDE_LAYOUT_BREAKPOINT`
（1000px）切換 `QSplitter` 的方向（`Qt.Horizontal`/`Qt.Vertical`）。切換方向後一定要重新
`setSizes([10**6, 10**6])`：`QSplitter` 換方向時沿用舊方向的像素值會變成不等寬/不等高，用兩個相同的
大數字讓 Qt 依可用空間等比例換算成 50/50。執行日誌面板高度不手動計算，交給 `QVBoxLayout` 原生分配
剩餘空間。整個中央 widget 再用 `QScrollArea(setWidgetResizable(True))` 包一層，視窗縮到很小時仍可捲動
看到全部內容。

右欄內部的垂直配額由 `MAP_STRETCH`(3) 與 `COORDS_STRETCH`(2) 決定，地圖另有 `MAP_MIN_HEIGHT`(320)
的下限。座標面板要不要顯示由 `_sync_coord_panels()` 一處判斷——「目前模式」與「是否收合」是兩個
獨立條件，分散到 `_switch_mode()` 與收合按鈕各自 `show()`/`hide()` 的話，收合狀態下切換模式會把
面板又叫回來。
