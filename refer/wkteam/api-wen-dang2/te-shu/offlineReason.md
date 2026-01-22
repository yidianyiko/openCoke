- 查询掉线原因

# 查询掉线原因

简要描述：

- 获取微信掉线原因，仅支持微信掉线情况下查看原因，本接口仅建议12小时内执行查询一次（慎重调用）

请求URL：

- http://域名地址/offlineReason

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wcId | 是 | string | 微信id |

返回数据：

| 参数名 | 类型 | 说明 |
| code | string | 1000成功，1001失败 |
| msg | string | 反馈信息 |
| wcId | string | 微信id |
| reason | string | 掉线原因（null则是在线） |

请求参数示例

```
{
    "wcId":"wxid_ctqh94e1he722"
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "获取离线原因成功",
    "data": [
        {
            "wcId": "wxid_ctqh94e1he722",
            "reason": null
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