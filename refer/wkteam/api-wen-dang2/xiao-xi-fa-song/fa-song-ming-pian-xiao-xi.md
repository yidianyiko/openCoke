- 发送名片消息

## 发送名片消息

请求URL：

- http://域名地址/sendNameCard

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | string | 登录实例标识 |
| wcId | 是 | string | 接收人微信id/群id |
| nameCardId | 是 | string | 要发送的名片微信id |

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
     "wId": "0000016e-abef-bb44-0002-dad3f6230dad",
     "wcId": "azhichao",
     "nameCardId": "wxid_uf44z2g3jge022"
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "发送名片成功",
    "data": {
        "type": 42,
        "msgId": 0,
        "newMsgId": 6240562811972867706,
        "createTime": 1641457349,
        "wcId": "wxid_rfdfvhobjai8d"
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