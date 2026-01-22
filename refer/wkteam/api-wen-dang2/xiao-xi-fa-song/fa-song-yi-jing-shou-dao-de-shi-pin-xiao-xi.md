- 转发视频消息

# 转发视频消息

简要描述：

- 根据消息回调收到的xml转发视频消息，适用于同内容大批量发送，可点击此处查看使用方式，第2大类4小节

请求URL：

- http://域名地址/sendRecvVideo

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | string | 登录实例标识 |
| wcId | 是 | string | 接收人微信id/群号id |
| content | 是 | string | xml视频内容 |

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
    "content": "<?xml version=\"1.0\"?>\n<msg>\n\t<videomsg aeskey=\"4f54430bcf53acfe9ef6b5d36d58e9f5\" cdnthumbaeskey=\"4f54430bcf53acfe9ef6b5d36d58e9f5\" cdnvideourl=\"306c020100046530630201000204f032c33602032f55f90204890260b402045e05b42a043e617570766964656f5f666661336336323865323964323566345f313537373433323130345f313533353034323731323139633662336333613434323131350204010400040201000400\" cdnthumburl=\"306c020100046530630201000204f032c33602032f55f90204890260b402045e05b42a043e617570766964656f5f666661336336323865323964323566345f313537373433323130345f313533353034323731323139633662336333613434323131350204010400040201000400\" length=\"7833957\" playlength=\"61\" cdnthumblength=\"12426\" cdnthumbwidth=\"288\" cdnthumbheight=\"512\" fromusername=\"zhongweiyu789\" md5=\"1ed727c57156b5f897e9e05a98912d80\" newmd5=\"d4f771f94ae15c4400b6dccff54068e9\" isad=\"0\" />\n</msg>\n"
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "转发视频消息成功",
    "data": {
        "type": null,
        "msgId": 697760525,
        "newMsgId": 5163231378817832136,
        "createTime": null,
        "wcId": null
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