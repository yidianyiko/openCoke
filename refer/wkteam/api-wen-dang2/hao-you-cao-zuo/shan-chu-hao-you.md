- 删除好友

# 删除好友

简要描述：

- 删除联系人

请求URL：

- http://域名地址/delContact

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 微信实列ID |
| wcId | 是 | String | 需删除的微信id |

返回数据：

| 参数名 | 类型 | 说明 |
| code | string | 1000成功，1001失败 |
| msg | string | 反馈信息 |
| data |

请求参数示例

```
{
   "wId": "0000016f-a2f0-03e3-0003-65e826091614",
   "wcId": "jack_623555049" 
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