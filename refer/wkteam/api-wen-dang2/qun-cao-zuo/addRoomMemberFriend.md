- 添加群成员为好友

## 添加群成员为好友

请求URL：

- http://域名/addRoomMemberFriend

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| chatRoomId | 是 | String | 群id |
| memberWcId | 是 | String | 群成员的wcId |
| content | 否 | String | 申请消息 |

请求参数示例

```
{
    "wId": "2c7a5bf6-e23d-4fb0-8f03-b90e844b539f",
    "chatRoomId": "18061832422@chatroom",
    "memberWcId": "wxid_9z89xz56uie22",
    "content": "你好"
}

```

成功返回示例

```
{
    "message": "添加群好友成功",
    "code": "1000",
    "data": "v3_020b3826fd030100000000003c5f0ccafe295400000001ea9a3dba12f95f6b60a0536a1adb690dcccc9bf58cc80765e6eb16b92b937608dcb0a9222f1d6f88492af63e5d2b8a1fd5aa9174f287a8a9dcc631bd81887305777604164a9b37af964bf@stranger"
}

```

错误返回示例

```
{
    "message": "由于对方的隐私设置，你无法通过群聊将其添加至通讯录。",
    "code": "1001",
    "data": null
}

```

返回数据：

| 参数名 | 类型 | 说明 |
| code | String | 1000成功1001失败 |
| msg | String | 反馈信息 |
| data | String | 添加好友凭证 |