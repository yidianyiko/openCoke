- 下载消息中的动图

## 下载消息中的动图

简要描述：

- 下载消息中的动图

请求URL：

- http://域名/getMsgEmoji

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | string | 登录实例标识 |
| msgId | 是 | int | 消息回调中返回 |
| content | 是 | string | 消息回调中返回，收到的emoji消息的xml数据 |

返回数据：

| 参数名 | 类型 | 说明 |
| code | string | 1000成功，1001失败 |
| msg | string | 反馈信息 |
| url | string | url地址 |

请求参数示例

```
{
    "wId": "fa94e1a8-a90d-4d22-b677-b7ca3dd93a7a",
    "msgId": 1711184317,
    "content": "zhongweiyu789:\n<msg><emoji fromusername=\"zhongweiyu789\" tousername=\"18365397499@chatroom\" type=\"1\" idbuffer=\"media:0_0\" md5=\"3563976960aa367af6d65c4f0b8bc9c4\" len=\"119971\" productid=\"\" androidmd5=\"3563976960aa367af6d65c4f0b8bc9c4\" androidlen=\"119971\" s60v3md5=\"3563976960aa367af6d65c4f0b8bc9c4\" s60v3len=\"119971\" s60v5md5=\"3563976960aa367af6d65c4f0b8bc9c4\" s60v5len=\"119971\" cdnurl=\"http://emoji.qpic.cn/wx_emoji/ulFbvhrzAnjIw2coZEkgcFLiaqbcIDH9ciaC32Hhy80iczDTTaaBciab7Q/\" designerid=\"\" thumburl=\"\" encrypturl=\"http://emoji.qpic.cn/wx_emoji/ulFbvhrzAnjIw2coZEkgcFLiaqbcIDH9cMrflH5p38pq4wzftFyxXjA/\" aeskey=\"f183af3d469b1806b58b8090b8b2a886\" externurl=\"http://emoji.qpic.cn/wx_emoji/GeicwdtUCicOkRC3FZEU6K0TjOBET2ic0FC8aOiaISHrQgVlr8oO8BjVmPoZ4aOKxs7f/\" externmd5=\"ef3c54cc09fc9edf9819969718404e7e\" width=\"170\" height=\"180\" tpurl=\"\" tpauthkey=\"\" attachedtext=\"\" attachedtextcolor=\"\" lensid=\"\"></emoji></msg>"
}

```

成功返回示例

```
{
    "message": "成功",
    "code": "1000",
    "data": {
        "url": "http://emoji.qpic.cn/wx_emoji/ulFbvhrzAnjIw2coZEkgcFLiaqbcIDH9ciaC32Hhy80iczDTTaaBciab7Q/"
    }
}

```

错误返回示例

```
{
    "message": "失败",
    "code": "1001",
    "data": null
}

```