- 获取企微联系人信息

## 获取企微联系人信息

简要描述：

- 获取联系人信息

请求URL：

- http://域名地址/getOpenImContact

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| wcId | 是 | String | 企微好友微信id |

请求参数示例

```

{
    "wId": "349be9b5-8734-45ce-811d-4e10ca568c67",
    "wcId": "2598498529278002@openim"
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "获取企微联系人信息成功",
    "data": {
        "userName": "2598498529278002@openim",
        "nickName": "E.Bot",
        "remark": "E.Bot/::@",
        "sex": 1,
        "bigHead": "https://wework.qpic.cn/wwpic/256156_XYiSic_UQaS_sVk_1675839963/0",
        "smallHead": "https://wework.qpic.cn/wwpic/256156_XYiSic_UQaS_sVk_1675839963/140",
        "wordingId": "41FC22D6BB9682BFEA7990D4303455ARI01@im.wxwork",
        "wording": "AI社群"
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
| userName | String | 企微好友微信id |
| nickName | String | 企微好友昵称 |
| remark | String | 企微好友备注 |
| sex | int | 性别 |
| bigHead | String | 大头像 |
| smallHead | String | 小头像 |
| wordingId | String | 企微所属企业Id |
| wording | String | 企微所属企业名称 |