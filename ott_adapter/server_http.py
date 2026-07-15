import json

MAX_CONTENT_SIZE = 1024 * 1024


def read_body(handler) -> bytes:
    length = int(handler.headers.get("Content-Length", 0))
    if length > MAX_CONTENT_SIZE:
        return b""
    return handler.rfile.read(length) if length else b""


def json_body(handler):
    try:
        return json.loads(read_body(handler) or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def json_resp(handler, data, status=200):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler._cors_headers()
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    try:
        handler.wfile.write(body)
    except (BrokenPipeError, ConnectionError):
        pass


def ott_err(handler, code: str, message: str, status: int = 400):
    json_resp(handler, {"error": {"code": code, "message": message}}, status)


def err(handler, msg, status=400):
    json_resp(handler, {"error": msg}, status)
