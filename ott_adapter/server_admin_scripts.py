import json
import subprocess
import sys
import time
from pathlib import Path

from .scheduler import run_script
from .script_safety import validate_script_file
from .server_http import err as _err, json_resp as _json_resp
from .server_script_helpers import script_safety_payload as _script_safety_payload
from .server_state import (
    SOURCE_KEY_RE,
    format_age as _format_age,
    rebuild_and_invalidate as _rebuild_and_invalidate,
    update_last_run as _update_last_run,
    validate_ott_json as _validate_ott_json,
)


class AdminScriptReadRunRoutes:
    data_dir: Path

    def _api_list_scripts(self):
        scripts_dir = self.data_dir / "scripts"
        scripts = []
        if scripts_dir.exists():
            for f in sorted(scripts_dir.glob("fetch_*.py")):
                key = f.stem.replace("fetch_", "", 1)
                content_file = self.data_dir / "content" / f"{key}.json"
                has_content = content_file.exists()
                content_age = (
                    time.time() - content_file.stat().st_mtime if has_content else None
                )
                scripts.append(
                    {
                        "name": f.name,
                        "source_key": key,
                        "size": f.stat().st_size,
                        "has_content": has_content,
                        "content_age_seconds": content_age,
                        "content_age_human": _format_age(content_age)
                        if content_age
                        else None,
                    }
                )
        _json_resp(self, {"scripts": scripts})

    # ── API: 脚本详情 ─────────────────────────────────────

    def _api_script_detail(self, name):
        if not SOURCE_KEY_RE.match(name):
            return _err(self, "无效的脚本名")

        script = self.data_dir / "scripts" / f"fetch_{name}.py"
        if not script.exists():
            return _err(self, f"脚本 'fetch_{name}.py' 不存在", 404)

        source = script.read_text(encoding="utf-8")
        content_file = self.data_dir / "content" / f"{name}.json"
        has_content = content_file.exists()
        content_preview = None
        if has_content:
            try:
                d = json.loads(content_file.read_text(encoding="utf-8"))
                content_preview = d.get("content", "")[:200]
            except Exception:
                pass

        _json_resp(
            self,
            {
                "name": script.name,
                "source_key": name,
                "size": script.stat().st_size,
                "source": source,
                "has_content": has_content,
                "content_preview": content_preview,
            },
        )

    # ── API: 脚本测试（dry-run）───────────────────────────

    def _api_script_test(self, name):
        if not SOURCE_KEY_RE.match(name):
            return _err(self, "无效的脚本名")

        script = self.data_dir / "scripts" / f"fetch_{name}.py"
        if not script.exists():
            return _err(self, f"脚本 'fetch_{name}.py' 不存在", 404)
        report = validate_script_file(script)
        if not report.valid:
            return _json_resp(self, _script_safety_payload(report), 400)

        # 测试模式：添加 --dry-run
        cmd = [sys.executable, str(script), "--dry-run"]
        if "--date" in script.read_text(encoding="utf-8"):
            cmd.extend(["--date", time.strftime("%Y-%m-%d")])

        start = time.time()
        try:
            r = subprocess.run(
                cmd,
                cwd=self.data_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            return _json_resp(
                self,
                {
                    "ok": False,
                    "error": "执行超时（30s）",
                    "duration": time.time() - start,
                },
            )
        except Exception as e:
            return _json_resp(
                self,
                {
                    "ok": False,
                    "error": str(e),
                    "duration": time.time() - start,
                },
            )

        elapsed = round(time.time() - start, 3)
        success = r.returncode == 0

        # 尝试解析 JSON 输出（如果脚本输出指向已有文件则读文件）
        preview_content = None
        validation = None
        if success:
            content_file = self.data_dir / "content" / f"{name}.json"
            if content_file.exists():
                try:
                    d = json.loads(content_file.read_text(encoding="utf-8"))
                    preview_content = (d.get("content", "") or "")[:200]
                    # schema 验证
                    validation = _validate_ott_json(d)
                except json.JSONDecodeError as e:
                    validation = {"valid": False, "error": f"JSON 解析失败: {e}"}
            else:
                validation = {"valid": False, "error": "测试未产生 content 文件"}

        _json_resp(
            self,
            {
                "ok": success,
                "exit_code": r.returncode,
                "duration": elapsed,
                "stdout": r.stdout[:2000] if r.stdout else "",
                "stderr": r.stderr[:2000] if r.stderr else "",
                "preview": preview_content,
                "validation": validation or {"valid": True},
            },
        )

    # ── API: 脚本运行（真实抓取）─────────────────────────

    def _api_script_run(self, name):
        if not SOURCE_KEY_RE.match(name):
            return _err(self, "无效的脚本名")

        script = self.data_dir / "scripts" / f"fetch_{name}.py"
        if not script.exists():
            return _err(self, f"脚本 'fetch_{name}.py' 不存在", 404)
        report = validate_script_file(script)
        if not report.valid:
            return _json_resp(self, _script_safety_payload(report), 400)

        success, output = run_script(script)

        if success:
            _update_last_run(self.data_dir, name)
        _rebuild_and_invalidate(self.data_dir)

        if success:
            content_file = self.data_dir / "content" / f"{name}.json"
            preview = None
            if content_file.exists():
                try:
                    d = json.loads(content_file.read_text(encoding="utf-8"))
                    preview = (d.get("content", "") or "")[:200]
                except Exception:
                    pass
            _json_resp(
                self,
                {
                    "ok": True,
                    "output": output[:2000] if output else "",
                    "preview": preview,
                },
            )
        else:
            _json_resp(
                self,
                {
                    "ok": False,
                    "error": output[:500] if output else "执行失败",
                },
            )

    # ── API: 创建脚本 ─────────────────────────────────────
