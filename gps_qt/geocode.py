"""地名搜尋：OpenStreetMap Nominatim。

刻意由 Python 端發送而不是在 map.js 裡 fetch()：Nominatim 的使用政策要求
每個請求帶可識別的 User-Agent、且每秒最多一次；在 QWebEngine 裡發出的
fetch() 帶的是瀏覽器的 User-Agent，改不掉也不合規，節流也難以控管。

用 QNetworkAccessManager 而非 urllib：它是非同步的，直接跑在 Qt 事件迴圈上，
搜尋時不會把 UI 卡住，也不需要為了一個查詢另外開 thread。
"""

import json

from PySide6.QtCore import QDateTime, QObject, QUrl, QUrlQuery, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Nominatim 政策要求能識別發出請求的應用程式；換成自己的專案位址也可以。
USER_AGENT = "PinDrift-GPS-Simulator/1.0 (https://github.com/garykillyou/PinDrift)"
MIN_REQUEST_INTERVAL_MS = 1000  # 政策上限：每秒最多 1 次
RESULT_LIMIT = 8


class Geocoder(QObject):
    """把一次地名查詢包成 results_ready / failed 兩個 signal。

    同時間只保留最後一次查詢：使用者連打兩次 Enter 時，前一個還沒回來的請求
    直接中止，避免舊結果比新結果晚到而覆蓋掉畫面。
    """

    results_ready = Signal(list)  # [{"name": str, "lat": float, "lon": float}, ...]
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._manager = QNetworkAccessManager(self)
        self._reply = None
        self._last_request_ms = 0

    def search(self, query):
        query = (query or "").strip()
        if not query:
            return
        now = QDateTime.currentMSecsSinceEpoch()
        if now - self._last_request_ms < MIN_REQUEST_INTERVAL_MS:
            self.failed.emit("搜尋請求太頻繁（Nominatim 限制每秒 1 次），請稍候再試")
            return
        self._last_request_ms = now

        self._abort_pending()
        url = QUrl(NOMINATIM_URL)
        params = QUrlQuery()
        params.addQueryItem("q", query)
        params.addQueryItem("format", "json")
        params.addQueryItem("limit", str(RESULT_LIMIT))
        params.addQueryItem("accept-language", "zh-TW")
        url.setQuery(params)

        request = QNetworkRequest(url)
        request.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, USER_AGENT)
        self._reply = self._manager.get(request)
        self._reply.finished.connect(self._on_finished)

    def _abort_pending(self):
        if self._reply is not None and not self._reply.isFinished():
            self._reply.abort()
        self._reply = None

    def _on_finished(self):
        reply = self.sender()
        reply.deleteLater()
        if reply is not self._reply:
            return  # 已被新的查詢取代，忽略這份過期結果
        self._reply = None

        if reply.error() == QNetworkReply.NetworkError.OperationCanceledError:
            return
        if reply.error() != QNetworkReply.NetworkError.NoError:
            self.failed.emit("搜尋失敗：" + reply.errorString())
            return

        try:
            raw = json.loads(bytes(reply.readAll().data()).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            self.failed.emit("搜尋結果解析失敗：" + str(e))
            return

        self.results_ready.emit(parse_results(raw))


def parse_results(raw):
    """把 Nominatim 的回應整理成 [{"name", "lat", "lon"}, ...]。

    抽成純函式方便測試；格式不合的項目直接跳過而不是讓整次查詢失敗——
    Nominatim 偶爾會回傳沒有座標的項目。
    """
    if not isinstance(raw, list):
        return []
    results = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            results.append({
                "name": str(item.get("display_name", "")),
                "lat": float(item["lat"]),
                "lon": float(item["lon"]),
            })
        except (KeyError, TypeError, ValueError):
            continue
    return results
