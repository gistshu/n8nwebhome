import json
import mimetypes
import os
import time
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

import psycopg


BASE_DIR = Path(__file__).resolve().parent
HOST = os.getenv("APP_HOST", "127.0.0.1")
PORT = int(os.getenv("APP_PORT", "8000"))
N8N_TCM_WEBHOOK_URL = os.getenv(
    "N8N_TCM_WEBHOOK_URL",
    # "http://127.0.0.1:5678/webhook-test/07d6d928-54fe-49d8-bec5-df537fff43c2",
    "http://localhost:5678/webhook-test/07d6d928-54fe-49d8-bec5-df537fff43c2",
)
PG_DSN = os.getenv("PG_DSN", "dbname=postgres user=shushu")


def get_db_connection() -> psycopg.Connection:
    return psycopg.connect(PG_DSN, autocommit=True)


def init_db() -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS tcm_consult_logs (
                    id BIGSERIAL PRIMARY KEY,
                    doctor_name TEXT NOT NULL,
                    question TEXT NOT NULL,
                    reply TEXT NOT NULL,
                    execution_seconds NUMERIC(10, 3) NOT NULL,
                    asked_at TIMESTAMPTZ NOT NULL,
                    session_id TEXT,
                    n8n_success BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tcm_consult_logs_doctor_asked_at
                ON tcm_consult_logs (doctor_name, asked_at DESC);
                """
            )


def json_response(handler: SimpleHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def read_json_body(handler: SimpleHTTPRequestHandler) -> dict[str, Any]:
    content_length = int(handler.headers.get("Content-Length", "0"))
    raw_body = handler.rfile.read(content_length) if content_length else b"{}"
    return json.loads(raw_body.decode("utf-8") or "{}")


def normalize_asked_at(sent_at: str | None) -> datetime:
    if sent_at:
        try:
            return datetime.fromisoformat(sent_at.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def call_n8n(payload: dict[str, Any]) -> tuple[bool, str, float]:
    request_body = json.dumps(payload).encode("utf-8")
    request = Request(
        N8N_TCM_WEBHOOK_URL,
        data=request_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started_at = time.perf_counter()

    try:
        with urlopen(request, timeout=180) as response:
            response_text = response.read().decode("utf-8")
            duration_seconds = round(time.perf_counter() - started_at, 3)
            data = None

            try:
                data = json.loads(response_text) if response_text else None
            except json.JSONDecodeError:
                data = None

            if isinstance(data, dict) and "success" in data and "reply" in data:
                return bool(data.get("success")), str(data.get("reply") or ""), duration_seconds

            return True, response_text or "(Webhook 無回傳內容)", duration_seconds
    except HTTPError as error:
        response_text = error.read().decode("utf-8", errors="replace")
        duration_seconds = round(time.perf_counter() - started_at, 3)
        return False, f"HTTP {error.code}: {response_text or 'Unknown error'}", duration_seconds
    except URLError as error:
        duration_seconds = round(time.perf_counter() - started_at, 3)
        return False, f"連線失敗：{error.reason}", duration_seconds
    except Exception as error:  # pragma: no cover - defensive fallback
        duration_seconds = round(time.perf_counter() - started_at, 3)
        return False, f"送出失敗：{error}", duration_seconds


def save_consult_log(
    doctor_name: str,
    question: str,
    reply: str,
    execution_seconds: float,
    asked_at: datetime,
    session_id: str | None,
    n8n_success: bool,
) -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tcm_consult_logs (
                    doctor_name,
                    question,
                    reply,
                    execution_seconds,
                    asked_at,
                    session_id,
                    n8n_success
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    doctor_name,
                    question,
                    reply,
                    execution_seconds,
                    asked_at,
                    session_id,
                    n8n_success,
                ),
            )


def fetch_recent_history(doctor_name: str, limit: int = 10) -> list[dict[str, Any]]:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT doctor_name, question, reply, execution_seconds, asked_at
                FROM tcm_consult_logs
                WHERE doctor_name = %s
                ORDER BY asked_at DESC, id DESC
                LIMIT %s
                """,
                (doctor_name, limit),
            )
            rows = cur.fetchall()

    history = []
    for doctor_name, question, reply, execution_seconds, asked_at in rows:
        history.append(
            {
                "doctorName": doctor_name,
                "question": question,
                "reply": reply,
                "executionSeconds": float(execution_seconds),
                "askedAt": asked_at.isoformat(),
            }
        )
    return history


class AppHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/tcm-consult/history":
            doctor_name = parse_qs(parsed.query).get("doctorName", [""])[0].strip()
            if not doctor_name:
                json_response(self, HTTPStatus.OK, {"history": []})
                return

            try:
                history = fetch_recent_history(doctor_name)
            except Exception as error:
                json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"讀取紀錄失敗：{error}"})
                return

            json_response(self, HTTPStatus.OK, {"history": history})
            return

        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/tcm-consult":
            json_response(self, HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return

        try:
            payload = read_json_body(self)
        except json.JSONDecodeError:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": "JSON 格式錯誤"})
            return

        doctor_name = str(payload.get("doctorName", "")).strip()
        question = str(payload.get("question", "")).strip()
        session_id = str(payload.get("sessionId", "")).strip() or None
        asked_at = normalize_asked_at(payload.get("sentAt"))

        if not doctor_name:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": "請先輸入醫師姓名"})
            return

        if not question:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": "請先輸入問診資訊"})
            return

        success, reply, duration_seconds = call_n8n(
            {
                "doctorName": doctor_name,
                "question": question,
                "sessionId": session_id,
                "sentAt": asked_at.isoformat(),
            }
        )

        try:
            save_consult_log(
                doctor_name=doctor_name,
                question=question,
                reply=reply,
                execution_seconds=duration_seconds,
                asked_at=asked_at,
                session_id=session_id,
                n8n_success=success,
            )
            history = fetch_recent_history(doctor_name)
        except Exception as error:
            json_response(
                self,
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "success": False,
                    "reply": reply,
                    "durationSeconds": duration_seconds,
                    "error": f"資料庫寫入失敗：{error}",
                },
            )
            return

        json_response(
            self,
            HTTPStatus.OK,
            {
                "success": success,
                "reply": reply,
                "durationSeconds": duration_seconds,
                "askedAt": asked_at.isoformat(),
                "history": history,
            },
        )

    def guess_type(self, path: str) -> str:
        if path.endswith(".js"):
            return "application/javascript; charset=utf-8"
        return mimetypes.guess_type(path)[0] or "application/octet-stream"


def main() -> None:
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), AppHandler)
    print(f"Serving on http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
