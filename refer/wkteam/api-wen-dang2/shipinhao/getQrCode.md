- 获取我的视频号二维码

## 获取我的视频号二维码

请求URL：

- http://域名/finder/getQrCode

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| meUserName | 是 | String | 自己的用户编码（获取个人主页接口返回的userName） |
| meRoleType | 是 | int | 自己的角色类型，根据角色关注（获取个人主页接口返回的roleType） |

请求参数示例

```
{
    "wId": "{{wId}}",
    "myUserName":"v2_060000231003b20faec8cae18a1ec5d0cb07eab077ba915250774edbea38082ea6b24af229@finder",
    "myRoleType": 3
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "获取视频号我的二维码成功",
    "data": {
        "qrUrl": "https://weixin.qq.com/f/EKhjEMLxIQHxoyT3vffquQ"
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