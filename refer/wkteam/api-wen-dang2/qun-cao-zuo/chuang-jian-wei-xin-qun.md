- 创建微信群

# 创建微信群

[!DANGER]

- 本接口为敏感接口，请查阅调用规范手册
- 创建后，手机上不会显示该群，往该群主动发条消息手机即可显示。

请求URL：

- http://域名地址/createChatroom

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| userList | 是 | String | 群成员微信id，多个已 "," 分割，（必须传输2个微信id以上才可创建群聊） |
| topic | 否 | String | 群名 |

请求参数示例

```
{
    "wId": "349be9b5-8734-45ce-811d-4e10ca568c67",
    "topic":"啦啦啦",
    "userList":"wxid_wl9qchkanp9u22,wxid_i6qsbbjenjuj22"
}

```

成功返回示例

```
{
    "message": "成功",
    "code": "1000",
    "data": {
        "chatRoomID": "22264491511@chatroom",
        "base64": "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoHBwYIDAoMDAsKCwsNDhIQDQ4RDgsLEBYQERMUFRUVDA8XGBYUGBIUFRT/2wBDAQMEBAUEBQkFBQkUDQsNFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBT/wAARCACLAIsDASIAAhEBAxEB/8QAHwAAAQUBXXXXXXXXXbSac8Uif8ATeM5/Jq9Zoo/s+l3f4f5DeYVX0X4/wCZw/hrQdTstXtprixEUYZ97mRSQCrY6H1IruKKK7KVJUY8sThq1XWlzSR//9k=",
        "status": 1
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

返回数据：

| 参数名 | 类型 | 说明 |
| code | String | 1000成功1001失败 |
| msg | String | 反馈信息 |
| data | JSONObject |  |
| chatRoomID | String | 群号 |
| base64 | String | 群二维码 |
| status | int | 状态 |