- 设置群待办消息

## 设置群待办消息

[!DANGER]

- 把群公告消息设置成待办消息

请求URL：

- http://域名/roomTodo

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| chatRoomId | 是 | String | 群id |
| newMsgId | 是 | int | 群公告的消息id(设置群公告成功后，回调返回newMsgId) |
| operType | 是 | int | 0:设置群待办 1:撤回群待办 |
| sign | 否 | int | 撤回传，设置待办成功后返回本字段 |

请求参数示例

```
{
    "wId": "xxxx",
    "chatRoomId": "xxxx@chatroom",
    "newMsgId": 123412341,
    "operType": 0
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

返回数据：

| 参数名 | 类型 | 说明 |
| code | String | 1000成功1001失败 |
| msg | String | 反馈信息 |
| sign | int | 撤销秘钥 |