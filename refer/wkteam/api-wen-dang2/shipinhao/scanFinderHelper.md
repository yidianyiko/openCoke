- 登录视频号助手

## 登录视频号助手

请求URL：

- http://域名/scanFinderHelper

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| url | 是 | String | 视频号助手官方二维码解析的地址（二维码） |

请求参数示例

```
{
    "wId": "2c7a5bf6-e23d-x-8f03-b90e844b539f",
    "url": "https://channels.weixin.qq.com/mobile/confirm_login.html?token=AQAAADuBfwIdyYlrciNBWQ"
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "处理成功",
    "data": {
        "sessionId": "BgAAoFaoS/vANMJKEyZH+Au/nki9zvLCL0es8VRNvfPrAC96a8lTJRzJHPzeUODIw7y/yQPlPGp5C07/D+hsIwjjOSx6q0m",
        "acctStatus": 1,
        "finderList": [
            {
                "finderUsername": "v2_060000231003b20faec8c6e18f10cc903ec3db0776955d3d97c6b329d6aa58693bcdb7ad1@finder",
                "nickname": "vvvv",
                "headImgUrl": "https://wx.qlogo.cn/finderhead/Q3auHgzwqOsJtnHiaiapZ4cv43GNBJkH0guXYeulzge7e7IQwHg/0",
                "coverImgUrl": "",
                "spamFlag": 0,
                "acctType": 1,
                "authIconType": 0,
                "ownerWxUin": 2207814660,
                "adminNickname": "hhh。",
                "categoryFlag": "0",
                "uniqId": "sphZ1RF6CMuZAn",
                "isMasterFinder": true
            }
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
| data | JSONObject |