- 发送文本消息

# 发送文本消息

请求URL：

- http://域名地址/sendText

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | string | 登录实例标识 |
| wcId | 是 | string | 接收人微信id/群id |
| content | 是 | string | 文本内容消息 |

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
------------------------ 好友消息 ------------------------------
{
    "wId": "0000016e-63eb-f319-0001-ed01076abf1f",
    "wcId": "azhichao",
    "content": "天行健，君子以自强不息"
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "处理成功",
    "data": {
        "type": 1,
        "msgId": 2562652205,
        "newMsgId": 4482117376572170921,
        "createTime": 1641457769,
        "wcId": "azhichao"
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