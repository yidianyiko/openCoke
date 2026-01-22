- 发送语音

# 发送语音

[!DANGER]

- 如需大批量微信发送同样微信内容可点击此处查看优化方式，第2大类4小节
- 音频格式（如 mp3）转 silk 格式可参考此类库自行转换：https://github.com/kn007/silk-v3-decoder/

请求URL：

- http://域名地址/sendVoice

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | string | 登录实例标识 |
| wcId | 是 | string | 接收人微信id/群id |
| content | 是 | string | 语音url （silk/amr 格式,可以下载消息中的语音返回silk格式） |
| length | 是 | int | 语音时长（回调消息xml数据中的voicelength字段） |

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
   "wId": "0000016f-a719-5b44-0003-a567f79011fc",
   "wcId":"jack_623555049",
   "content": "https://xc-1300726975.cos.ap-shanghai.myqcloud.com/msgVoice/e17dd0a9-5c59-4a54-a3cd-1a4817f5dd29-1579005558791.silk",
    "length": 1
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "发送语音消息成功",
    "data": {
        "type": null,
        "msgId": 697760541,
        "newMsgId": 1375821081513076275,
        "createTime": 1641458029,
        "wcId": "jack_623555049"
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