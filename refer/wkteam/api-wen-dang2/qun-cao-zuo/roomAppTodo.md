- 设置群待办消息

## 设置群待办消息

[!DANGER]

- 把小程序消息设置成待办消息

请求URL：

- http://域名/roomAppTodo

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| chatRoomId | 是 | String | 群id |
| newMsgId | 是 | int | 小程序的消息id(小程序消息回调返回newMsgid) |
| title | 是 | 小程序标题 | 小程序消息回调中取 |
| pagePath | 是 | 小程序跳转地址 | 小程序消息回调中取 |
| userName | 是 | 小程序id | 小程序回调中取 |
| sendWcId | 是 | 原小程序的发送者id | 小程序回调中取 |
| sign | 否 | int | 撤回传，设置待办成功后返回本字段 |

请求参数示例

```
{
    "wId": "2c7a5bf6-e23d-4fb0-8f03-b9ae844b539f",
    "chatRoomId": "25553320410@chatroom",
    "newMsgId": 128659030295046943,
    "title":"寄快递，用圆通",
    "pagePath":"pages/tabBar/index/index.html?sampshare=%7B%22i%22%3A%22oXJy05PxRKRmhJLHqmAn_NE9YrFc%22%2C%22p%22%3A%22pages%2FtabBar%2Findex%2Findex%22%2C%22d%22%3A0%2C%22m%22%3A%22%E8%BD%AC%E5%8F%91%E6%B6%88%E6%81%AF%E5%8D%A1%E7%89%87%22%7D",
    "userName":"gh_f9d9fca26a50@app",
    "sendWcId":"wxid_ylxtflc0p8b22"

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