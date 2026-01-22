- 私信图片

## 私信图片

请求URL：

- http://域名/privateSendImg

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| toUserName | 是 | String | 视频号用户的编码 |
| sessionId | 是 | String | 通过/getSessionId接口获取 |
| imgUrl | 是 | String | 图片地址 |

[!DANGER]小提示：

- 第一次私信无法发送图片，需对方回复后方可发送

请求参数示例

```
{
    "wId": "2c7a5bf6-e23d-x-8f03-b90e844b539f",
    "toUserName": "v2_060000231003b20faec8cae18a1ec5d0cb07ea33b077ba915250774edbea38082ea6b24af229@finder",
    "sessionId": "a37c87fbfb8c07ca21d29bea6e3feef1cd740982cfda8407bde2dc2ccbba7f0c@findermsg",
    "imgUrl": "https://pics7.182.40.194.50/feed/5bafa40f4bfbfbed6b32473c12ec31fdd.jpeg@f_auto?token=11b9f52e463efdcbd43acc274d55350"
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "处理成功",
    "data": {
        "newMsgId": 1248576160896589973
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
| data | JSONObject |