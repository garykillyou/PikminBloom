# 📍 iPhone GPS 路線模擬器

> 免費、免越獄、免 iTunes，在 Windows 上模擬 iPhone GPS 定位的桌面工具。支援 iOS 26。

![Python](https://img.shields.io/badge/Python-3.14+-blue?logo=python)
![Platform](https://img.shields.io/badge/Platform-Windows-blue?logo=windows)
![iOS](https://img.shields.io/badge/ios-26-black?logo=apple)
![License](https://img.shields.io/badge/License-MIT-green)

---

## ✨ 功能

- 🗺 **路線移動模式** — 設定多個座標點，讓 iPhone 沿路線緩慢移動
- 📌 **固定定位模式** — 將 iPhone 定位釘在指定座標不動
- 📋 **座標貼上** — 從地圖複製的「緯度, 經度」可直接貼進固定座標欄位，自動拆成兩欄帶入
- ⭐ **最愛地點** — 儲存常用地點或路線，下次一鍵載入（清單依目前模式自動篩選）
- 📥 **KML 路線匯入** — 直接匯入 Google Earth / Google 地圖匯出的 KML 檔案，自動轉成路線最愛
- 🚶 **速度調整** — 支援步行、慢跑、騎車、開車等速度預設，也可自訂 km/h
- 🔄 **循環模式** — 路線走完自動折返，來回往復（走到端點才判定，中途可隨時勾選／取消）
- ↔ **隨時切換方向** — 路線模式可隨時在「往起點 / 往終點」之間切換，連線全程保持不中斷
- 📊 **即時進度** — 顯示目前座標、完成百分比，以及路線總距離與預計時間
- 💾 **記住上次設定** — 自動保留上次的路線座標點與移動速度
- 🌓 **深色 / 淺色主題** — 一鍵切換，偏好會自動記住
- 🚀 **一鍵啟動** — `run.bat` 會自動偵測並啟動 tunneld，不必自己開系統管理員終端機

---

## 📋 系統需求

| 項目 | 需求 |
|------|------|
| 作業系統 | Windows 11 |
| Python | 3.14 64-bit（開發與實測環境） |
| iPhone | iOS 26 |
| 連線方式 | USB（不需 iTunes） |

---

## 🚀 安裝步驟

**1. 安裝 Python 3.14 64-bit**

前往 [python.org](https://www.python.org/downloads/) 下載並安裝，記得勾選 **Add Python to PATH**。

**2. 下載本專案**

```bash
git clone https://github.com/garykillyou/PikminBloom.git
cd PikminBloom
```

**3. 安裝相依套件**

```bash
pip install -r requirements.txt
```

---

## ▶️ 使用方式

### Step 1：iPhone 開啟開發者模式

設定 → 隱私與安全性 → 開發者模式 → 開啟（需重開機）

### Step 2：雙擊 `run.bat` 啟動

`run.bat` 會自動做兩件事：

1. 偵測 tunneld 是否已經在執行（檢查 `127.0.0.1:49151`）。沒有的話會跳出 **UAC 視窗**要求系統管理員權限，
   同意後自動啟動 tunneld，並等待幾秒讓它就緒。
2. 以 `pythonw` 啟動 App（不顯示主控台視窗，cmd 視窗會自動關閉，只留下程式視窗）。

> tunneld 的視窗請保持開著，關掉就會斷線。

<details>
<summary>手動啟動（不使用 run.bat）</summary>

以**系統管理員**開啟命令提示字元：

```bash
python -m pymobiledevice3 remote tunneld
```

等到出現以下訊息後保持視窗開著：
```
INFO: Uvicorn running on http://127.0.0.1:49151
```

再開一個新的命令提示字元執行 App：

```bash
python -m gps_qt.main
```

</details>

---

## 🖥️ 介面說明

### 路線移動模式
1. 在座標表格中輸入路線點（緯度、經度、備註），可用「新增點」增加、點該列的「刪除」移除
2. 選擇移動速度（預設按鈕或自訂 km/h），標題列會即時顯示總距離、預計時間與節點數
3. 按「開始模擬」沿路線往終點走
4. 按「往起點」隨時改成往回走；走回去的途中按鈕會變成「往終點」，再按一次就切回前進
5. 勾選「循環模式（來回）」後，走到端點會自動折返、來回往復
6. 按「停止」暫停在目前座標（連線保持，不會恢復真實定位）
7. 按「恢復真實定位」才會真正斷線，iPhone 恢復真實 GPS（移動中需先按「停止」）

### 固定定位模式
1. 切換到「固定定位」模式
2. 輸入緯度/經度，或使用快速選擇；也可以把「24.1368, 120.6862」這種字串直接貼進任一欄自動帶入
3. 按「固定定位」釘住座標
4. 按「停止」保持在目前座標（連線保持，不會恢復真實定位）
5. 按「恢復真實定位」才會真正斷線，iPhone 恢復真實 GPS

### 最愛地點
- 清單只會顯示目前模式對應的項目，按鈕也跟著切換：
  - 固定定位模式：「儲存目前座標」
  - 路線移動模式：「儲存目前路線」、「匯入 KML 路線」
- 「匯入 KML 路線」可選擇 KML 檔案，自動解析路線座標並存成路線最愛
- 點「載入」一鍵套用（會同時切換到對應的模式），「編輯」可重新命名，「刪除」可移除
- 資料儲存於 `gps_favorites.json`，重開 App 後保留

### 主題切換
- 點右上角的主題按鈕，即可在深色／淺色介面間切換
- 偏好會存於 `gps_settings.json`，下次啟動自動套用上次選擇

### 視窗位置記憶
- 關閉 App 時會記住視窗的大小、位置與是否最大化，下次啟動自動還原（多螢幕環境會回到上次使用的那一台螢幕）
- 若上次使用的螢幕已經拔掉或解析度改變，會自動退回預設大小、由 Windows 決定擺放位置，不會讓視窗開在看不見的地方
- 同時也會記住上次的路線座標點與移動速度

---

## 📁 檔案結構

```
PikminBloom/
├── gps_qt/             # 主程式（GUI App，PySide6 + qasync + qt-material）
├── requirements.txt    # 相依套件
├── run.bat             # 啟動捷徑（自動起 tunneld + 免主控台視窗啟動）
├── start_tunneld.ps1   # 偵測並以系統管理員啟動 tunneld
├── gps_favorites.json  # 最愛地點資料（自動產生）
├── gps_settings.json   # 主題、視窗位置、上次路線與速度（自動產生）
└── README.md
```

---

## ⚠️ 注意事項

- 本工具僅供學習、測試用途
- 部分遊戲或 App 有反作弊機制，使用需自行承擔風險
- **按「停止」不會恢復真實定位**：連線會保持著、定位停在目前座標。要讓 iPhone 回到真實 GPS，
  必須按「恢復真實定位」（或直接關閉 App / tunneld）

---

## 🛠️ 技術說明

本專案使用 [pymobiledevice3](https://github.com/doronz88/pymobiledevice3) 與 iPhone 通訊。

iOS 26 需透過 RemoteXPC tunnel 連線，因此需要先啟動 `tunneld` 服務建立加密通道，再透過 DVT（Developer Tools）的 `LocationSimulation` 服務注入模擬座標。

App 全程只建立一條長連線：開始、切換方向、停止都只是改變狀態，不會重連；唯有按下「恢復真實定位」才會
關閉連線並讓裝置回到真實 GPS。

---

## 📄 License

MIT License
