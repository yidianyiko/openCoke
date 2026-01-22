- 获取企微联系人列表

## 获取企微联系人列表

简要描述：

- 获取联系人信息

请求URL：

- http://域名地址/getImAddressList

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |

请求参数示例

```

{
    "wId": "349be9b5-8734-45ce-811d-4e10ca568c67"
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "获取企微联系人列表成功",
    "data": [
        {
            "userName": "25984982670495377@openim",
            "nickName": "张",
            "remark": "",
            "sex": 1,
            "bigHead": "http://wework.qpic.cn/bizmail/5VlSBLWBUtiaHEuWhTlTLAbkvDCI9YkNJRwTC8clhjU9BEqjUuD1zdg/0",
            "smallHead": "http://wework.qpic.cn/bizmail/5VlSBLWBUtiaHEuWhTlTLAbkvDCI9YkNJRwTC8clhjU9BEqjUuD1zdg/140",
            "wordingId": "31464B9A2FA768BDA1F418BB1F28BE46RI01@im.wxwork",
            "appId": "3552365301"
        },
        {
            "userName": "25984984569242180@openim",
            "nickName": "明周",
            "remark": "",
            "sex": 1,
            "bigHead": "https://wework.qpic.cn/wwhead/duc2TvpEgST9hicuyypLEKNaicnxdBY5Lmc7Q2wNs5yltbE4X3OzGuOdqHdHwSTPq5BvaEByzuCn8/0",
            "smallHead": "https://wework.qpic.cn/wwhead/duc2TvpEgST9hicuyypLEKNaicnxdBY5Lmc7Q2wNs5yltbE4X3OzGuOdqHdHwSTPq5BvaEByzuCn8/140",
            "wordingId": "6D61E058344848AB6DF55D0156BA0C19RI01@im.wxwork",
            "appId": "3552365301"
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
| userName | String | 企微好友微信id |
| nickName | String | 企微好友昵称 |
| remark | String | 企微好友备注 |
| sex | int | 性别 |
| bigHead | String | 大头像 |
| smallHead | String | 小头像 |
| wordingId | String | 企微所属企业Id |
| appId | String | 保留字段 |