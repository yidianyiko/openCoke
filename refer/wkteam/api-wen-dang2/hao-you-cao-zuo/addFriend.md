- 添加好友

# 添加好友

[!DANGER]

- 本接口需在线3天后使用，且必须查看调用规范手册说明

简要描述：

- 添加微信好友

请求URL：

- http://域名地址/addUser

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | string | 登录实例标识 |
| v1 | 是 | string | v1 从搜索好友接口获取 |
| v2 | 是 | string | v2 从搜索好友接口获取 |
| type | 是 | int | 添加来源3 ：微信号搜索4 ：QQ好友8 ：来自群聊15：手机号 |
| verify | 是 | String | 验证消息 |

返回数据：

| 参数名 | 类型 | 说明 |
| code | string | 1000成功，1001失败 |
| msg | string | 反馈信息 |

请求参数示例

```
{
   "wId": "0000016f-a2f0-03e3-0003-65e826091614",
   "v1": "v1_aaf94e13d0058cdc888e388b98952e0fc23212d180e4dacb38b96dfe4b078c488e72772f907517470ac0b9b7311826da@stranger",
   "v2": "v2_13ced007472228cd1545feecf78b99f9a57a88843374513747afc7ac25d8a4cccb77590b7a9b01a96c941e047d137bbb@stranger",
   "type": 3,
   "verify": ""

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