- 获取通讯录列表

## 获取通讯录列表

简要描述：

- 获取通讯录列表

请求URL：

- http://域名地址/getAddressList

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |

[!DANGER]小提示：

- 获取通讯录列表之前，必须调用初始化通讯录列表接口。
- 此接口不会返回好友/群的详细信息，如需获取详细信息，请调用获取联系人详情接口
- 本接口的返回群聊的是保存到通讯录的群聊详细规范点击这里(第5大类2小节)

请求参数示例

```
{
    "wId": "6a696578-16ea-4edc-ac8b-e609bca39c69"
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "获取通讯录成功",
    "data": {
        "chatrooms": [
            ""
        ],
        "friends": [
            ""
        ],
        "ghs": [
            ""
        ],
        "others": [
            ""
        ]
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
| chatrooms | JSONArray | 群组列表群组返回为null的处理方法(第5大类3小节) |
| friends | JSONArray | 好友列表不包含企微好友，获取企微好友列表点击这里 |
| ghs | JSONArray | 公众号列表 |
| others | JSONArray | 微信其他相关 |