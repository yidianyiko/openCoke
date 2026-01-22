- 查询微信是否在线

# 查询微信是否在线

[!DANGER]

- 如需实时判断在线，消息回调中会返回下线的通知

简要描述：

- 查询是否在线

请求URL：

- http://域名地址/isOnline

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | string | 登录实例标识 |

返回数据：

| 参数名 | 类型 | 说明 |
| code | string | 1000成功（在线），1001失败（离线） |
| msg | string | 反馈信息 |

请求参数示例

```
{
    "wId": "0000016e-abcd-0ea8-0002-d8c2dfdb0bf3"
}

```

成功返回示例

```
{
    "message": "成功",
    "code": "1000",
    "data": {
        "isOnline": true
    }
}

```

失败返回示例

```
{
    "message": "成功",
    "code": "1000",
    "data": {
        "isOnline": false
    }
}

```