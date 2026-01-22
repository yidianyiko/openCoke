- 发送文件

## 发送文件

[!DANGER]如需大批量微信发送同样微信内容可点击此处查看优化方式，第2大类4小节

请求URL：

- http://域名地址/sendFileBase64

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | string | 登录实例标识 |
| wcId | 是 | string | 接收方微信id/群id |
| fileName | 是 | string | 文件名 |
| base64 | 是 | string | 文件Base64可点击此处验证Base64格式是否正确 |

返回数据：

| 参数名 | 类型 | 说明 |
| code | string | 1000成功，1001失败 |
| msg | string | 反馈信息 |
| data |  |  |
| data.type | int | 类型 |
| data.msgId | long | 消息msgId |
| data.newMsgId | long | 消息newMsgId |
| data.createTime | long | 消息发送时间戳 |
| data.wcId | string | 消息接收方id |

请求参数示例

```
{
   "wId": "0000016f-a805-4715-0001-848f9a297a40",
   "wcId":"jack_623555049",
   "fileName": "123.txt",
   "base64": "data:text/plain;base64,5oiR5piv576O5Li955qE5rWL6K+V5paH5Lu2Cg=="
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "发送文件消息成功",
    "data": {
        "type": 6,
        "msgId": 697760551,
        "newMsgId": 8262558808731059065,
        "createTime": 1641458290,
        "wcId": "jack_623555049"
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