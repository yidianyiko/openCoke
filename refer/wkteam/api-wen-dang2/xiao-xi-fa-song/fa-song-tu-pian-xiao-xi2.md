- 发送图片消息

# 发送图片消息

[!DANGER]如需大批量微信发送同样微信内容可点击此处查看优化方式，第2大类4小节

请求URL：

- http://域名地址/sendImage2

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | string | 登录实例标识 |
| wcId | 是 | string | 接收人微信id/群id |
| content | 是 | string | 图片url链接 |

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
    "wId": "0000016e-63eb-f319-0001-ed01076abf1f",
    "wcId": "LoChaX",
    "content": "http://photocdn.sohu.com/20120323/Img338614056.jpg"
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "发送图片消息成功",
    "data": {
        "type": null,
        "msgId": 697760516,
        "newMsgId": 901023126355472137,
        "createTime": 0,
        "wcId": "LoChaX"
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