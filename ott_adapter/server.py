"""OTT 适配器 HTTP 服务 + Web UI。"""

import json
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote

SOURCE_KEY_RE = re.compile(r"^[^\\\./]+$")

class OttHandler(BaseHTTPRequestHandler):
    data_dir = Path(".")

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        path = unquote(self.path)
        if path == "/" or path == "/index.html":
            self._serve_web_ui()
        elif path == "/registry_index.json":
            self._serve_file(self.data_dir / "registry_index.json")
        elif path.startswith("/content/") and path.endswith(".json"):
            source_key = path[len("/content/"):-len(".json")]
            if not SOURCE_KEY_RE.match(source_key):
                self.send_error(400, "Invalid source_key")
                return
            self._serve_file(self.data_dir / "content" / f"{source_key}.json")
        else:
            self.send_error(404)

    def _serve_file(self, path):
        if not path.exists():
            self.send_error(404, f"Not found: {path.name}")
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _serve_web_ui(self):
        try:
            p = self.data_dir / "registry_index.json"
            catalog = json.loads(p.read_text()) if p.exists() else {"sources": []}
        except Exception:
            catalog = {"sources": []}

        sources = catalog.get("sources", [])
        rows = "".join(
            f'<tr><td>{s.get("label",s["source_key"])}</td>'
            f'<td>{s.get("description","")}</td>'
            f'<td>{s.get("charCount","?")}</td>'
            f'<td><a href="#" onclick="load(\'{s["source_key"]}\')">查看</a></td></tr>'
            for s in sources
        ) or '<tr><td colspan="4" style="text-align:center;color:#999;padding:40px">暂无文本</td></tr>'

        html = f'''<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8"><title>OTT 文本中心</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#f5f5f5;color:#333;padding:20px}}
.c{{max-width:800px;margin:0 auto}}
h1{{text-align:center;margin:20px 0}}
.sub{{text-align:center;color:#666;margin-bottom:30px;font-size:14px}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.1)}}
th,td{{padding:12px 16px;text-align:left;border-bottom:1px solid #eee}}
th{{background:#fafafa;font-weight:600;color:#555}}
a{{color:#1890ff;text-decoration:none}}
#view{{display:none;margin-top:20px;background:#fff;border-radius:8px;padding:20px;box-shadow:0 2px 8px rgba(0,0,0,.1);position:relative}}
#view .back{{position:absolute;top:20px;right:20px;cursor:pointer;color:#1890ff}}
#view .text{{line-height:1.8;white-space:pre-wrap;word-break:break-all;margin-top:10px}}
.status{{text-align:center;margin-top:20px;font-size:13px;color:#999}}
</style></head><body><div class="c">
<h1>OTT 文本中心</h1><p class="sub">开源中文打字文本 · 本地适配器</p>
<table><thead><tr><th>标题</th><th>描述</th><th>字数</th><th>操作</th></tr></thead><tbody>{rows}</tbody></table>
<div id="view"><span class="back" onclick="hide()">← 返回</span><h2 id="t"></h2><div class="meta" id="m"></div><div class="text" id="x"></div></div>
<p class="status">本工具不提供任何文本内容，所有数据由用户本地抓取生成。</p>
</div>
<script>
function load(k){{fetch("/content/"+k+".json").then(r=>r.json()).then(d=>{{document.querySelector("table").style.display="none";document.getElementById("view").style.display="block";document.getElementById("t").textContent=d.title||k;document.getElementById("m").textContent=(d.metadata?.description||"")+" · "+(d.content?.length||0)+" 字";document.getElementById("x").textContent=d.content||"(空)"}})}}
function hide(){{document.querySelector("table").style.display="";document.getElementById("view").style.display="none"}}
</script></body></html>'''

        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start_server(port, data_dir):
    OttHandler.data_dir = Path(data_dir)
    server = HTTPServer(("127.0.0.1", port), OttHandler)
    print(f"OTT 适配器已启动: http://127.0.0.1:{port}")
    print(f"数据目录: {data_dir}")
    print("Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止.")
        server.server_close()
