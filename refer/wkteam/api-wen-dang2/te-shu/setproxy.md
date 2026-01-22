- 动态设置代理IP

# 动态设置代理IP

简要描述：动态设置代理IP

请求URL：

- http://域名地址/setproxy

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wcId | 是 | string | 微信id |
| proxyIp | 是 | string | 代理IP+端口 |
| proxyUser | 是 | string | 代理IP平台账号 |
| proxyPassword | 是 | string | 代理IP平台密码 |

返回数据：

| 参数名 | 类型 | 说明 |
| code | string | 1000成功，1001失败 |
| msg | string | 反馈信息 |

请求参数示例

```

    {
    "wcId":"wxid_ctqh94e1e722",
    "proxyIp":"121.229.46.245:3829",
    "proxyUser":"x",
    "proxyPassword":"x"
    }

```

成功返回示例

```
{
    "message": "成功",
    "code": "1000",
    "data": null
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