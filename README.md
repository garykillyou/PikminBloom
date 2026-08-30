# 📍 iPhone GPS 路線模擬器

> 免費、免越獄、免 iTunes，在 Windows 上模擬 iPhone GPS 定位的桌面工具。支援 iOS 17 / 18 / 26+。

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python)
![Platform](https://img.shields.io/badge/Platform-Windows-blue?logo=windows)
![iOS](https://img.shields.io/badge/ios-26-black?logo=apple)
![License](https://img.shields.io/badge/License-MIT-green)

---

## ✨ 功能

- 🗺 **路線移動模式** — 設定多個座標點，讓 iPhone 沿路線緩慢移動
- 📌 **固定定位模式** — 將 iPhone 定位釘在指定座標不動
- ⭐ **最愛地點** — 儲存常用地點或路線，下次一鍵載入
- 📥 **KML 路線匯入** — 直接匯入 Google Earth / Google 地圖匯出的 KML 檔案，自動轉成路線最愛
- 🚶 **速度調整** — 支援步行、慢跑、騎車、開車等速度預設
- 🔄 **循環模式** — 路線走完自動從頭再走
- 📊 **即時進度** — 顯示目前座標與完成百分比
- 🌓 **深色 / 淺色主題** — 一鍵切換，偏好會自動記住

---

## 📋 系統需求

| 項目 | 需求 |
|------|------|
| 作業系統 | Windows 11 |
| Python | 3.11 64-bit 以上 |
| iPhone | iOS 26 |
| 連線方式 | USB（不需 iTunes） |

---

## 🚀 安裝步驟

**1. 安裝 Python 3.11 64-bit**

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

### Step 2：啟動 tunneld（需系統管理員）

以**系統管理員**開啟命令提示字元：

```bash
python -m pymobiledevice3 remote tunneld
```

等到出現以下訊息後保持視窗開著：
```
INFO: Uvicorn running on http://127.0.0.1:49151
```

### Step 3：執行 App

開新的命令提示字元：

```bash
python gps_app.py
```

也可以直接雙擊 `run.bat`，會以不顯示主控台視窗的方式啟動。

---

## 🖥️ 介面說明

### 路線移動模式
1. 在座標表格中輸入路線點（緯度、經度、備註）
2. 選擇移動速度
3. 按「▶ 開始模擬」
4. 按「⏹ 停止」恢復真實定位

### 固定定位模式
1. 切換到「📌 固定定位」模式
2. 輸入緯度/經度，或使用快速選擇
3. 按「📌 固定定位」
4. 按「⏹ 停止」恢復真實定位

### 最愛地點
- 點「＋ 儲存目前路線」或「＋ 儲存目前座標」儲存
- 點「＋ 匯入 KML 路線」選擇 KML 檔案，自動解析路線座標並存成路線最愛
- 點「載入」一鍵套用
- 資料儲存於 `gps_favorites.json`，重開 App 後保留

### 主題切換
- 點右上角的主題按鈕，即可在深色／淺色介面間切換
- 偏好會存於 `gps_settings.json`，下次啟動自動套用上次選擇

---

## 📁 檔案結構

```
PikminBloom/
├── gps_app.py          # 主程式（GUI App）
├── requirements.txt    # 相依套件
├── run.bat             # 免主控台視窗啟動捷徑
├── gps_favorites.json  # 最愛地點資料（自動產生）
├── gps_settings.json   # 主題等偏好設定（自動產生）
└── README.md
```

---

## ⚠️ 注意事項

- 本工具僅供學習、測試用途
- 部分遊戲或 App 有反作弊機制，使用需自行承擔風險
- 停止模擬後 iPhone 會自動恢復真實定位

---

## 🛠️ 技術說明

本專案使用 [pymobiledevice3](https://github.com/doronz88/pymobiledevice3) 與 iPhone 通訊。

iOS 17+ 需透過 RemoteXPC tunnel 連線，因此需要先啟動 `tunneld` 服務建立加密通道，再透過 DVT（Developer Tools）的 `LocationSimulation` 服務注入模擬座標。

---

## 📄 License

MIT License
