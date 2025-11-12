# 纯净微信消息 Flask 服务部署指南

## 依赖清单
- Python 3.9+
- `requirements.txt`：仅包含 `Flask`

## 配置说明
- 可选文件 `config.example.json` 字段：
  - `appid`：微信应用 AppID（保留占位，当前服务不直接调用公众号接口）
  - `appsecret`：微信应用密钥（占位）
  - `token`：签名 Token（占位）。如需接入官方签名校验，可在后续扩展中启用
  - `encodingAESKey`：消息加密密钥（占位）
  - `port`：服务监听端口，默认 `8090`

## 代码检出
- `git clone <repo-url>`
- `cd minimal_wechat_flask`

## 安装与启动
- 创建虚拟环境并安装依赖：
  - `python -m venv .venv`
  - `. .venv/bin/activate`
  - `pip install -r requirements.txt`
- 启动服务：
  - `python app.py`（默认监听 `0.0.0.0:8090`）
  - 或设置端口：`PORT=8091 python app.py`

## 接口规范
- 接入 URL：`POST /message`
- 请求体为 JSON，关键字段：
  - `wcId`：来源设备/会话标识
  - `messageType`：消息类型，仅支持 `60001` 文本、`60014` 引用
  - `data.fromUser`、`data.toUser`、`data.content`
- 行为：
  - 文本与引用消息返回 `{"status":"success","type": "text|quote","message":"received"}`
  - 其他类型返回 `{"status":"success","message":"not supported message type"}`

## 验证步骤
- 文本消息：
  - `curl -s -X POST http://localhost:8090/message -H 'Content-Type: application/json' -d '{"wcId":"wxid_test","messageType":"60001","data":{"fromUser":"wxid_from","toUser":"wxid_to","content":"hello"}}'`
- 引用消息（XML 内容会自动提取）：
  - `curl -s -X POST http://localhost:8090/message -H 'Content-Type: application/json' -d '{"wcId":"wxid_test","messageType":"60014","data":{"fromUser":"wxid_from","toUser":"wxid_to","content":"<msg><content>quoted text</content></msg>"}}'`
- 非核心类型：
  - `curl -s -X POST http://localhost:8090/message -H 'Content-Type: application/json' -d '{"wcId":"wxid_test","messageType":"60002","data":{"fromUser":"wxid_from","toUser":"wxid_to","content":"img"}}'`

## 说明
- 服务仅保留微信消息接入 URL `/message`，且只处理文本与引用消息；图片/视频/语音等类型已禁用
- 如需接入官方签名校验（`token/timestamp/nonce/signature`）或公众号 XML 格式，可在此模块基础上扩展

