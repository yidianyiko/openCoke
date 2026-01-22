- 获取私信联系人信息

## 获取私信联系人信息

请求URL：

- http://域名/finder/getContactDetails

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
| contactUserName | 是 | String | 私信联系人的username |

请求参数示例

```
{
    "wId": "{{wId}}",
    "contactUserName": "fv1_552fe39c023a38d299394e3832455d574586ae4e399e51f3f17d414691ae85b@findermsgstranger",
    "myUserName":"v2_060000231003b20faec8cae18a1ec5d0cb07eab077ba915250774edbea38082ea6b24af229@finder",
    "myRoleType": 3
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "查询视频号私信联系人详情成功",
    "data": [
        {
            "wxUsernameV5": "v5_020b0a16610401000000000023390adabe0bb3000000b1afa7d87e3dd43ef4317a780e33c2996857e4fdf7e8b0f6772a3d0e16c79d1a10bf247770dfef7bd0280d9b6a78205e554b90a5a94de2a3349cfcf4@stranger",
            "signature": "从",
            "nickname": "。",
            "headUrl": "https://wx.qlogo.cn/mmhead/ver_1/IJW4tmWjmDDKtcD2BcK876rfEDuYNqhayoFJOK1DfxX3z3BfecTRJiael8s9ibNjKiaeVjnOkiabTyatdxxnIbmGWfa2Shv4GONDiaIhQCFvXA/132",
            "msgInfo": {
                "sessionId": "552fe39c023a38d299394e3832455d5774586ae399e51f3f17d414691ae85b@findermsg",
                "msgUsername": "fv1_552fe39c023a38d299394e3832455d57586ae4e399e51f3f17d414691ae85b@findermsgstranger"
            },
            "username": "fv1_552fe39c023a38d299394e3832455774586ae4e399e51f3f17d414691ae85b@findermsgstranger",
            "extInfo": {
                "country": "CN",
                "province": "Jiangsu",
                "city": "Nanjing",
                "sex": 1
            }
        }
    ]
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