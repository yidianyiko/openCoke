- 撤回消息

## 撤回消息

请求URL：

- http://域名地址/revokeMsg

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | string | 登录实例标识 |
| wcId | 是 | string | 接收方微信id/群id |
| msgId | 是 | long | 消息msgId(发送类接口返回的msgId) |
| newMsgId | 是 | long | 消息newMsgId(发送类接口返回的newMsgId) |
| createTime | 是 | long | 发送时间 |

返回数据：

| 参数名 | 类型 | 说明 |
| code | string | 1000成功，1001失败 |
| msg | string | 反馈信息 |

请求参数示例

```
{
    "wId": "12491ae9-62aa-4f7a-83e6-9db4e9f28e3c",
    "wcId": "wxid_1dfgh4fs8vz22",
    "msgId": 697760203,
    "newMsgId": 4792296942111367533,
    "createTime": 1641456307
}

```

成功返回示例

```
{
    "message": "成功",
    "code": "1000",
    "data": null
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