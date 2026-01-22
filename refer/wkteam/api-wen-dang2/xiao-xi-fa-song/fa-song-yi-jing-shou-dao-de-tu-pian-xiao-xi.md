- 转发图片消息

# 转发图片消息

简要描述：

- 根据消息回调收到的xml转发图片消息，适用于同内容大批量发送，可点击此处查看使用方式，第2大类4小节

请求URL：

- http://域名地址/sendRecvImage

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | string | 登录实例标识 |
| wcId | 是 | string | 接收人微信id/群id |
| content | 是 | string | xml图片内容 |

返回数据：

| 参数名 | 类型 | 说明 |
| code | string | 1000成功，1001失败 |
| msg | string | 反馈信息 |
| data |  |  |
| data.type | int | 类型 |
| data.msgId | long | 消息msgId |
| data.newMsgId | long | 消息newMsgId |
| data.createTime | long | 消息发送时间戳 |
| data.wcId | string | 消息接收方id |

请求参数示例

```
{
    "wId": "0000016f-4621-dde5-0002-390493cab4dc",
    "wcId": "zhongweiyu789",
    "content": "<?xml version=\"1.0\"?>\n<msg>\n\t<img aeskey=\"849481a442044ad3a3a8130c94d2b591\" encryver=\"0\" cdnthumbaeskey=\"849481a442044ad3a3a8130c94d2b591\" cdnthumburl=\"3053020100044c304a0201000204e7d9caed02032f55f90204900060b402045e05acc00425617570696d675f386634626639356134343465613063665f31353737343330323038303739020401053a010201000400\" cdnthumblength=\"3310\" cdnthumbheight=\"80\" cdnthumbwidth=\"120\" cdnmidheight=\"0\" cdnmidwidth=\"0\" cdnhdheight=\"0\" cdnhdwidth=\"0\" cdnmidimgurl=\"3053020100044c304a0201000204e7d9caed02032f55f90204900060b402045e05acc00425617570696d675f386634626639356134343465613063665f31353737343330323038303739020401053a010201000400\" length=\"19842\" cdnbigimgurl=\"3053020100044c304a0201000204e7d9caed02032f55f90204900060b402045e05acc00425617570696d675f386634626639356134343465613063665f31353737343330323038303739020401053a010201000400\" hdlength=\"99007\" md5=\"39fec3c8e1ebad09ef4289b9e712a716\" hevc_mid_size=\"13869\" />\n</msg>\n"
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "转发图片消息成功",
    "data": {
        "type": null,
        "msgId": 697760529,
        "newMsgId": 8689175729438895373,
        "createTime": 0,
        "wcId": "zhongweiyu789"
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