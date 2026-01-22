- 扫码入群

# 扫码入群

[!DANGER]好友将群二维码发送给机器人，机器人调用本接口将自动识别入群

请求URL：

- http://域名地址/scanJoinRoom

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | string | 登录实例标识 |
| url | 是 | string | 群二维码url（二维码解析后的url） |
| type | 否 | int | 操作类型，默认00: 进群1:返回群名称及人数10:返回原始html数据 |

返回数据：

| 参数名 | 类型 | 说明 |
| code | string | 1000成功，1001失败 |
| msg | string | 反馈信息 |

请求参数示例

```
{
   "wId": "0000016f-a340-c2d7-0003-6ab83bc1e64a",
   "url": "https://weixinxxx"
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