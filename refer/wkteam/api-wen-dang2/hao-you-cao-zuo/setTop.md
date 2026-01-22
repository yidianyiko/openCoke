- 设置聊天置顶

## 设置聊天置顶

简要描述：

- 设置好友/群的会话聊天置顶

请求URL：

- http://域名/setTop

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| wcId | 是 | String | 好友id/群id |
| operType | 是 | int | 0：取消 1：置顶 |

请求参数示例

```
{
    "wId": "xxxxxx",
    "wcId": "24608539283@chatroom",
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
| data | JSONObject |