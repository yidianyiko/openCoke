- 取消消息接收

# 取消消息接收

简要描述：

- 取消消息接收

请求URL：

- http://域名地址/cancelHttpCallbackUrl

请求方式：

- POST

请求头Headers：

- Authorization：login接口返回
- Content-Type：application/json

无参数

返回数据：

| 参数名 | 类型 | 说明 |
| code | string | 1000成功，1001失败 |
| msg | string | 反馈信息 |

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