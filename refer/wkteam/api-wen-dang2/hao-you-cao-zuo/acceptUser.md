- 同意添加好友

# 同意添加好友

[!DANGER]

- 本接口需在线3天后使用，且必须查看调用规范手册说明

简要描述：

- 同意添加好友

请求URL：

- http://域名地址/acceptUser

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | string | 登录实例标识 |
| v1 | 是 | string | v1（从消息回调中取） |
| v2 | 是 | string | v2（从消息回调中取） |
| type | 是 | int | 取回调中的scene来源 |

返回数据：

| 参数名 | 类型 | 说明 |
| code | string | 1000成功，1001失败 |
| msg | string | 反馈信息 |

请求参数示例

```
{
    "wId": "349be9b5-8734-45ce-811d-4e10ca568c67",
    "v1": "v1_54fec2c3b452e9ec75505d5b062c0de28c08e3770a1f50a7a2d9ca509a2f82e4b03aaed0a37875c73bd5c35b91e2b060@stranger",
    "v2": "v4_000b708f0b04000001000000000014cf2b671dd639a279577eece15e1000000050ded0b020927e3c97896a09d47e6e9ef867bb94625d7dde9f2ebf03bb305a7aeddb554cc6f3f06e7d5a5327255425494854a71da02c88157e83f491afa8c17a3768b04cc1456c4a981e119a9eb93cf42a34bedc769a6c9dbe19597b2efb6d8d86cbaf97baac97ab61bda9fba80aeacf426a52b13e1d7854fc@stranger",
    "type":3
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