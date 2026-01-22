- 获取我的二维码

## 获取我的二维码

简要描述：

- 获取我的二维码

请求URL：

- http://域名地址/getQrCode

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |

请求参数示例

```
{
    "wId": "0000016f-a2f0-03e3-0003-65e826091614"
}

```

成功返回示例

```
{
    "message": "成功",
    "code": "1000",
    "data": {
        "qrCodeUrl": "http://qr.topscan.com/api.php?text=http://weixin.qq.com/x/QapmFw5pgyAShaPk2cLM",
        "uuId": "QapmFw5pgyAShaPk2cLM"
    }
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

返回数据：

| 参数名 | 类型 | 说明 |
| code | String | 1000成功1001失败 |
| msg | String | 反馈信息 |
| data | JSONObject |