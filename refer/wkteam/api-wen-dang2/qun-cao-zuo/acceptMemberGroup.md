- 自动通过群（url）

## 自动通过群（url）

简要描述：

- 自动通过群（url）

请求URL：

- http://域名地址/acceptUrl

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：Authorization值（登录获取二维码信息接口中返回的认证信息值）

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | string | 登录实例标识 |
| url | 是 | string | 原始 url，好友发送的入群邀请卡片信息链接(回调中取) |

返回数据：

| 参数名 | 类型 | 说明 |
| code | string | 1000成功，1001失败 |
| msg | string | 反馈信息 |
| data |

请求参数示例

```
{
     "wId": "0000016f-b270-b2cd-0000-4e27e92f4502",
     "url": "http://shmmsns.qpic.cn/mmsns/CJ35Z2cnZA0zggcHCKIiaqOu0wO1gaOTaxL2Wd9StGfS1GdbbfKvJic1icfjfMXia7iaAd1B4fgN61g4/150"
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