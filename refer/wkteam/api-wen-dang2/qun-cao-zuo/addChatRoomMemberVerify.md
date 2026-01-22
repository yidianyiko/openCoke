- 邀请群成员（开启群验证）

## 邀请群成员（开启群验证）

[!DANGER]

- 若群开启邀请确认，仅能通过本接口邀请群成员

请求URL：

- http://域名/addChatRoomMemberVerify

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| chatRoomId | 是 | String | 群id |
| userList | 是 | number | 邀请好友的id |
| reason | 是 | String | 邀请理由（管理员查看，不得为空） |

请求参数示例

```
{
    "wId": "2c7a5bf6-e23d-4fb0-8f03-b90e844b539f",
    "chatRoomId": "1806832422@chatroom",
    "userList": "wxid_i6sbbjenjuj22",
    "reason":"拉个发小入群"
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
| data | JSONObject |