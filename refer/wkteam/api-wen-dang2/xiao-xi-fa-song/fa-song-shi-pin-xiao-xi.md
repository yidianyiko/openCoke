- 发送视频消息

# 发送视频消息

[!DANGER]如需大批量微信发送同样微信内容可点击此处查看优化方式，第2大类4小节

请求URL：

- http://域名地址/sendVideo

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | string | 登录实例标识 |
| wcId | 是 | string | 接收人微信id/群id |
| path | 是 | string | 视频url链接 |
| thumbPath | 是 | string | 视频封面url链接（50KB以内） |

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
    "wId": "0000016e-a1f1-f0d9-0002-425ea1a28d22",
    "wcId": "jack_623555049",
    "path": "https://wkgjonlines.oss-cn-shenzhen.aliyuncs.com/movies/20191113/d7c616569ac342ad1fa8e3301682844e.mp4",
    "thumbPath": "http://pic23.nipic.com/20120902/8068495_150602391000_2.jpg"
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "发送视频消息成功",
    "data": {
        "type": null,
        "msgId": 697760511,
        "newMsgId": 3289648069366716802,
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