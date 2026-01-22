- 发送emoji表情

## 发送emoji表情

简要描述：

- 发送emoji动图表情

请求URL：

- http://域名地址/sendEmoji

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | string | 登录实例标识 |
| wcId | 是 | string | 接收人微信id/群id |
| imageMd5 | 是 | string | 取回调中xml中md5字段值 |
| imgSize | 是 | string | 取回调中xml中len字段值 |

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
    "wId": "00000171-78df-0aad-000c-70e4a3ce7d70",
    "wcId": "LoChaX",
    "imageMd5": "4cc7540a85b5b6cf4ba14e9f4ae08b7c",
    "imgSize":"102357"
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "发送Emoji消息成功",
    "data": {
        "type": null,
        "msgId": 697760499,
        "newMsgId": 5012973909876748200,
        "createTime": null,
        "wcId": null
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