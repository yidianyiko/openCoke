- 群管理操作

## 群管理操作

简要描述：

- 群管理操作

请求URL：

- http://域名/operateChatRoom

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| chatRoomId | 是 | String | 群号 |
| wcId | 是 | String | 群成员微信id，多个用 "," 分割 |
| type | 是 | int | 1：添加群管理（可添加多个微信id） 2：删除群管理（可删除多个） 3：转让（只能转让一个微信号） |

请求参数示例

```
{
    "wId": "xxxxxx",
    "chatRoomId": "24608539283@chatroom",
    "wcId": "wxid_0zssg6z7ivlm22"，
    "type": 3
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