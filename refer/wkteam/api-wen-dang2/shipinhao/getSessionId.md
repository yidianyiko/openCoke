- 获取私信SessionId

## 获取私信SessionId

请求URL：

- http://域名/getSessionId

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| toUserName | 是 | String | 视频号用户的编码 |
| myUserName | 是 | String | 自己的用户编码 |
| type | 是 | int | 类型 1是视频号身份  2是自身微信号身份type=1时，myUserName必传 type=2时，myUserName为空 |

请求参数示例

```
{
    "wId": "{{wId}}",
    "toUserName": "v2_060000231003b20faec8c6e78010c3d4c605eb3cb077f16e37c172145877400390b1170a0299@finder",
    "myUserName": "xxxxxxxxxxxxxxxxxxxxxxxxxxx@finder",
    "type": 1
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "处理成功",
    "data": {
        "sessionId": "69fd3a9cc1180847d8b5a1533bf285b99a83784cfd4cfdadea78974509359c74@findermsg",
        "enableAction": 0,
        "toUsername": "v2_060000231003b20faec8c6e78010c3d4c605eb3cb077f16e37c172145877400390b1170a0299@finder"
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