- 转发文件消息

# 转发文件消息

简要描述：

- 根据消息回调收到的xml转发文件消息，适用于同内容大批量发送，可点击此处查看使用方式，第2大类4小节

请求URL：

- http://域名地址/sendRecvFile

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | string | 登录实例标识 |
| wcId | 是 | string | 接收人微信id/群id |
| content | 是 | string | xml文件内容 |

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
   "content": "xxx"
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "转发文件成功",
    "data": {
        "type": 6,
        "msgId": 697760535,
        "newMsgId": 6957007917217750754,
        "createTime": 1641457929,
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