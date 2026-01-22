- 群聊@

# 群聊@

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
| wcId | 是 | string | 接收方群id |
| content | 是 | string | 文本内容消息（@的微信昵称需要自己拼接，必须拼接艾特符号，不然不生效） |
| at | 是 | string | 艾特的微信id（多个以逗号分开）群主或者管理员如果是艾特全部的人，则直接填写'notify@all' |

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
 "wId": "0000016f-8911-484a-0001-db2943fc2786",
 "wcId": "22270365143@chatroom",
 "at": "wxid_lr6j4nononb921,wxid_i6qsbbjenjuj22",
 "content": "@E云Team_Mr Li@你微笑时真美 测试"
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
        "wcId": "22270365143@chatroom"
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