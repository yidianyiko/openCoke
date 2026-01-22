- 获取联系人信息

## 获取联系人信息

简要描述：

- 获取联系人信息

请求URL：

- http://域名地址/getContact

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| wcId | 是 | String | 好友微信id/群id,多个好友/群 以","分隔每次最多支持20个微信/群号,本接口每次调用请随机间隔300ms-800ms之间 |

请求参数示例

```

{
    "wId": "349be9b5-8734-45ce-811d-4e10ca568c67",
    "wcId": "LoChaX,wxid_wl9qchkanp9u22"
}

```

成功返回示例

```
{
    "message": "成功",
    "code": "1000",
    "data": [
        {
            "userName": "test558666",
            "nickName": "追风少年666",
            "remark": "",
            "signature": "66666",
            "sex": 1,
            "aliasName": "test558666",
            "country": "CN",
            "bigHead": "http://wx.qlogo.cn/mmhead/PiajxSqBRaEL8iaRQBnStn37LYat3fREC4Y2iaStECzbX3icxntWBhWQ3w/0",
            "smallHead": "http://wx.qlogo.cn/mmhead/PiajxSqBRaEL8iaRQBnStn37LYat3fREC4Y2iaStECzbX3icxntWBhWQ3w/132",
            "labelList": "",
            "v1": "v1_584e7774024c79af0e7304bf7afba775b31bf075651c16c964b1b5bf16369924ebf1ee7bc151c1feee1979e1dd40f0dd@stranger"
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
| data | JSONObject |  |
| userName | String | 微信id |
| nickName | String | 昵称 |
| remark | String | 备注 |
| signature | String | 签名 |
| sex | int | 性别 |
| aliasName | String | 微信号 |
| country | String | 国家 |
| bigHead | String | 大头像 |
| smallHead | String | 小头像 |
| labelList | String | 标签列表 |
| v1 | String | 用户的wxId，都是以v1开头的一串数值，v2数据，则是作为v1数据的辅助 |