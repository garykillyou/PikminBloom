# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 專案概述

單一檔案 Python/Tkinter 桌面工具，透過 `pymobiledevice3` 模擬 iPhone（iOS 17+）的 GPS 定位，
免越獄、免 iTunes，僅需 USB 連線。整個應用程式邏輯都在 [gps_app.py](gps_app.py) 一個檔案中，
沒有其他模組、套件或子目錄。

## 常用指令

```bash
# 安裝相依套件
pip install -r requirements.txt

# 執行前，需先在「系統管理員」的終端機啟動 tunneld（建立 iOS 17+ 的 RemoteXPC 加密通道）
pymobiledevice3 remote tunneld

# 另開一般終端機執行 App
python gps_app.py
```

也可以雙擊 [run.bat](run.bat) 啟動（用 `pythonw` 執行，不顯示主控台視窗，啟動後 cmd 視窗會自動關閉，只留下程式視窗）。

目前專案沒有測試、lint 或 build 設定（無 test/CI/lint 相關檔案）。

## 架構重點

### 執行流程（連接 iPhone 的關鍵鏈路）
1. `tunneld` 必須以系統管理員權限先啟動，建立 iOS 17+ 的 RemoteXPC 通道。
2. App 啟動後，透過 `pymobiledevice3.tunneld.api.get_tunneld_devices()` 找到裝置（取第一台，`rsds[0]`）。
3. 用 `DvtProvider(rsd)` 開啟 DVT（Developer Tools）連線，再用 `LocationSimulation(dvt)` 取得定位模擬服務。
4. `sim.set(lat, lon)` 注入座標；停止時呼叫 `sim.clear()` 恢復真實 GPS 定位。
5. 這段邏輯分別實作在 `GPSApp._simulate()`（路線模式）與 `_simulate_pin()`（固定定位模式）中，兩者高度相似但各自獨立，修改其中一個時要留意另一個是否也需要同步修改。

### 兩種模式（由 `self.mode` StringVar 控制）
- **路線模式（route）**：多個座標點依序移動。`interpolate_points()` 會依照 `haversine()` 算出的距離與設定速度（m/s），把每段路線切成每秒一個內插點，逐點呼叫 `sim.set()` 並 `asyncio.sleep(1.0)`。支援 `loop_var` 循環模式（跑完從頭再來）。
- **固定定位模式（pin）**：呼叫一次 `sim.set(lat, lon)` 後，用 `while not self.stop_event.is_set(): await asyncio.sleep(0.5)` 持續保持定位，直到使用者按停止。

### 執行緒與非同步整合
- 按下「開始模擬」後，UI 主執行緒會另開 `self.sim_thread`（`threading.Thread(daemon=True)`），內部用 `asyncio.run()` 執行 `_simulate()` / `_simulate_pin()`（因為 `pymobiledevice3` 的 DVT/LocationSimulation API 是 async）。
- 背景執行緒中若要更新 Tkinter UI（進度條、日誌、按鈕狀態），一律要透過 `self.after(0, ...)` 排回主執行緒，不可直接操作 widget。
- `self.stop_event`（`threading.Event`）是跨執行緒的停止訊號，`_stop()` 只負責 `set()`，實際清理與恢復定位在對應的 `_simulate*()` coroutine 內完成。

### 最愛地點（Favorites）
- 儲存在執行檔同目錄的 `gps_favorites.json`（`FAVORITES_FILE`），由 `load_favorites()` / `save_favorites()` 讀寫，內容是 list of dict，`type` 欄位為 `"pin"` 或 `"route"`。
- UI 清單（`_refresh_fav_list`）與載入邏輯（`_load_fav`）都靠這個 `type` 欄位分派要切到哪個模式、要填哪些欄位；新增最愛欄位時要同步確認存檔格式與讀取端都對得起來。

### UI 結構
- 全部手刻 `tkinter`/`ttk`（無第三方 UI 框架），深色主題色票集中定義在檔案開頭（`BG`/`BG2`/`BG3`/`ACCENT`/`ACCENT2`/`SUCCESS`/`DANGER`/`TEXT`/`TEXT2`）。
- `_build_ui()` 一次性建構所有面板；模式切換靠 `_switch_mode()` 用 `pack()`/`pack_forget()` 顯示或隱藏對應的 Frame（`pin_frame`、`speed_frame_ref`、`route_section` 等），而不是建立多個視窗或使用 `Notebook`。
- 路線點表格（`route_container`）是動態產生的：每次新增/刪除點都呼叫 `_refresh_route_rows()` 整個重建所有列，而不是局部更新。
