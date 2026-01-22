- 查询账号中在线的微信列表

# 查询账号中在线的微信列表

简要描述：

- 此接口应用场景是查询在线的wid和wcid列表

请求URL：

- http://域名地址/queryLoginWx

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

无参数：

返回数据：

| 参数名 | 类型 | 说明 |
| code | string | 1000成功（在线），1001失败（离线） |
| message | string | 反馈信息 |
| wcId | string | 微信id |
| wId | string | 登录实例标识 |

请求参数示例

```
{    

}

```

成功返回示例

```
{
    "code": "1000",
    "message": "成功",
    "data": [
        {
            "wcId": "wxid_i6qsbbjenju2",
            "wId": "72223018-7f2a-4f4f-bfa3-26e47dbd61"
        }
    ]
}

```

失败返回示例

```
{
    "code": "1001",
    "message": "失败"
}

```