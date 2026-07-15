import json
from pathlib import Path

from .script_safety import validate_script_source
from .server_http import err as _err, json_body as _json_body, json_resp as _json_resp
from .server_script_helpers import (
    script_safety_payload as _script_safety_payload,
    script_template as _script_template,
)
from .server_state import (
    SOURCE_KEY_RE,
    _schedule_lock,
    calc_next_run as _calc_next_run,
    get_schedules as _get_schedules,
    get_write_lock as _get_write_lock,
    rebuild_and_invalidate as _rebuild_and_invalidate,
    save_schedules as _save_schedules,
)


class AdminScriptMutationRoutes:
    data_dir: Path

    def _api_create_script(self):
        body = _json_body(self)
        if body is None:
            return _err(self, "无效的 JSON 请求体")

        source_key = (body.get("source_key") or "").strip()
        source_code = body.get("source_code") or ""

        if not source_key:
            return _err(self, "source_key 必填")
        if not SOURCE_KEY_RE.match(source_key):
            return _err(self, "source_key 只能含字母数字下划线")

        scripts_dir = self.data_dir / "scripts"
        script_file = scripts_dir / f"fetch_{source_key}.py"
        if script_file.exists():
            return _err(self, f"脚本 fetch_{source_key}.py 已存在", 409)

        # 使用模板填充
        if not source_code.strip():
            source_code = _script_template(source_key)
        report = validate_script_source(source_code, f"fetch_{source_key}.py")
        if not report.valid:
            return _json_resp(self, _script_safety_payload(report), 400)

        scripts_dir.mkdir(parents=True, exist_ok=True)
        script_file.write_text(source_code, encoding="utf-8")
        _json_resp(
            self,
            {"ok": True, "name": f"fetch_{source_key}.py", "source_key": source_key},
            201,
        )

    # ── API: 保存脚本源码 ─────────────────────────────────

    def _api_script_save(self, name):
        if not SOURCE_KEY_RE.match(name):
            return _err(self, "无效的脚本名")

        script = self.data_dir / "scripts" / f"fetch_{name}.py"
        if not script.exists():
            return _err(self, f"脚本 'fetch_{name}.py' 不存在", 404)

        body = _json_body(self)
        if body is None:
            return _err(self, "无效的 JSON 请求体")

        source_code = body.get("source_code", "")
        if not source_code.strip():
            return _err(self, "源码不可为空")
        report = validate_script_source(source_code, f"fetch_{name}.py")
        if not report.valid:
            return _json_resp(self, _script_safety_payload(report), 400)

        script.write_text(source_code, encoding="utf-8")
        _json_resp(self, {"ok": True, "name": f"fetch_{name}.py"})

    # ── API: 重命名脚本 ───────────────────────────────────

    def _api_script_rename(self, name):
        if not SOURCE_KEY_RE.match(name):
            return _err(self, "无效的脚本名")

        body = _json_body(self)
        if body is None:
            return _err(self, "无效的 JSON 请求体")

        new_key = (body.get("new_key") or "").strip()
        if not new_key:
            return _err(self, "new_key 必填")
        if not SOURCE_KEY_RE.match(new_key):
            return _err(self, "new_key 只能含字母数字下划线")

        dd = self.data_dir
        old_script = dd / "scripts" / f"fetch_{name}.py"
        new_script = dd / "scripts" / f"fetch_{new_key}.py"
        if not old_script.exists():
            return _err(self, f"脚本 'fetch_{name}.py' 不存在", 404)
        if new_script.exists():
            return _err(self, f"目标脚本 'fetch_{new_key}.py' 已存在", 409)

        old_script.rename(new_script)

        # 也重命名对应的 content 文件（如果存在）
        old_content = dd / "content" / f"{name}.json"
        new_content = dd / "content" / f"{new_key}.json"
        if old_content.exists():
            with _get_write_lock(name):
                try:
                    d = json.loads(old_content.read_text(encoding="utf-8"))
                    d["source_key"] = new_key
                    tmp = new_content.with_suffix(".tmp")
                    tmp.write_text(
                        json.dumps(d, ensure_ascii=False, separators=(",", ":")),
                        encoding="utf-8",
                    )
                    tmp.replace(new_content)
                    old_content.unlink()
                except Exception:
                    pass

        _rebuild_and_invalidate(dd)
        _json_resp(self, {"ok": True, "old_key": name, "new_key": new_key})

    # ── API: Cron 配置 ────────────────────────────────────

    def _api_script_cron_get(self, name):
        if not SOURCE_KEY_RE.match(name):
            return _err(self, "无效的脚本名")

        schedules = _get_schedules(self.data_dir)
        sched = schedules.get("schedules", {}).get(
            name,
            {
                "interval": "manual",
                "enabled": False,
                "last_run": None,
                "next_run": None,
            },
        )
        _json_resp(self, sched)

    def _api_script_cron_set(self, name):
        if not SOURCE_KEY_RE.match(name):
            return _err(self, "无效的脚本名")

        body = _json_body(self)
        if body is None:
            return _err(self, "无效的 JSON 请求体")

        interval = body.get("interval", "manual")
        if interval not in ("manual", "hourly", "daily", "weekly"):
            return _err(self, "interval 可选: manual / hourly / daily / weekly")

        enabled = body.get("enabled", interval != "manual")

        with _schedule_lock:
            schedules = _get_schedules(self.data_dir)
            if "schedules" not in schedules:
                schedules["schedules"] = {}

            prev = schedules["schedules"].get(name, {})
            last_run = prev.get("last_run")

            schedules["schedules"][name] = {
                "interval": interval,
                "enabled": enabled,
                "last_run": last_run,
                "next_run": _calc_next_run(interval, last_run) if enabled else None,
            }

            _save_schedules(self.data_dir, schedules)
        _json_resp(self, {"ok": True, **schedules["schedules"][name]})

    # ── API: 最近条目（仪表盘用，不含全文） ────────────────
