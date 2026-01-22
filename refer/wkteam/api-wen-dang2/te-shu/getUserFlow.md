- 查询使用流量

# 查询使用流量

简要描述：

- 查看服务器中所有用户使用流量

请求URL：

- http://域名地址/getUserFlow

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：空

返回数据：

| 参数名 | 类型 | 说明 |
| code | string | 1000成功，1001失败 |
| msg | string | 反馈信息 |
| account | string | 开发者账号 |
| nickName | string | 微信昵称 |
| wcId | string | 微信id |
| flow | string | 使用流量 |
| size | int | 使用流量（以B为单位） |
| wid | string | 登录实例标识 |

请求参数示例

```
{
    空
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "处理成功",
    "data": [
        {
            "account": "1875323779",
            "nickName": "小叶子",
            "wcId": "wxid_2hq3u6nrd822",
            "flow": "262MB",
            "size": 274971864,
            "wid": "7cee86c5-5275-43ec-f1-aa38f9589083"
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