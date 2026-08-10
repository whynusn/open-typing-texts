"""OTT Repo v1 control-plane routes.

Serves a self-describing ``/ott-repo.json`` manifest pointing at this
adapter's own data plane (OTT Core v1 Service/Static Profile), so clients
can subscribe to a local adapter as a source repository.

Spec: docs/repo-manifest-spec.md — a Repository distributes pointers to
sources, never text content itself.
"""

from __future__ import annotations

import time
from pathlib import Path

from .server_http import json_resp as _json_resp
from .server_state import read_index as _read_index

REPO_VERSION = "1.0"


def _base_url(handler) -> str:
    """Derive the externally reachable base URL for this adapter.

    Prefer the ``Host`` header (works behind a reverse proxy / LAN access),
    fall back to 127.0.0.1 with the bound port.
    """
    host = handler.headers.get("Host", "").strip()
    if host:
        return f"http://{host}"
    port = handler.server.server_address[1]
    return f"http://127.0.0.1:{port}"


class RepoManifestRoutes:
    data_dir: Path

    def _ott_repo_manifest(self):
        base = _base_url(self)
        index = _read_index(self.data_dir)
        sources = index.get("sources", [])
        has_content = bool(sources)

        manifest = {
            "protocol": "ott-repo",
            "version": REPO_VERSION,
            "type": "repository",
            "repo_id": "local",
            "name": "本地 OTT 适配器",
            "description": "本机 OTT 适配器（OTT Core v1 数据面）自描述仓库",
            "maintainer": {"name": "open-typing-texts"},
            "license": "MIT",
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
            "mirrors": [
                {"url": f"{base}/ott-repo.json", "priority": 1},
            ],
            "requires": {"ott_core": ">=1.0"},
            "sources": [
                {
                    "type": "ott-instance",
                    "authority": "local",
                    "label": "本地 OTT 适配器",
                    "endpoints": [
                        {"url": base, "profile": "service", "priority": 1},
                        {"url": base, "profile": "static", "priority": 2},
                    ],
                    "tags": ["local"],
                    "default_enabled": True,
                }
            ],
        }
        if has_content:
            manifest["description"] = (
                "本机 OTT 适配器（OTT Core v1 数据面）自描述仓库，"
                f"当前收录 {len(sources)} 个文本源"
            )
        _json_resp(self, manifest)
