## 数据来源

- 来源名称：
- 来源网址：
- 合规说明：已确认本地抓取行为符合目标网站 robots.txt、服务条款及当地法律法规。

## 本地验证

```bash
uv run ott-adapter validate-script scripts/fetch_<source>.py
uv run ott-adapter validate-script scripts/fetch_<source>.py --run
uv run ott-adapter validate content/<source>.json
uv run ott-adapter validate --data-dir .
```

请粘贴 PASS/FAIL 摘要，不要提交 `content/` 真实抓取内容。

## 运行要求

- 是否需要账号、cookie、token 或特殊环境变量：
- 是否有频率限制或人工确认步骤：
