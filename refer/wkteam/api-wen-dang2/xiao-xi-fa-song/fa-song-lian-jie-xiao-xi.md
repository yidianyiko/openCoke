- 发送链接

## 发送链接

简要描述：

- 发送链接

请求URL：

- http://域名地址/sendUrl

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | string | 登录实例标识 |
| wcId | 是 | string | 接收人微信id/群id |
| title | 是 | string | 标题 |
| url | 是 | string | 链接 |
| description | 是 | string | 描述 |
| thumbUrl | 是 | string | 图标url（JPG/PNG格式,50K以内） |

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
    "wId": "0000016f-63d2-ea61-000e-a659a75ea445",
    "wcId": "jack_623555049",
    "title": "这是测试链接",
    "url": "https://timgsa.182.40.194.50/timg?image&quality=80&size=b9999_10000&sec=1577945612638&di=81a0281095a337037abf85f29929b55f&imgtype=0&src=http%3A%2F%2Fimage5.92bizhi.com%2Funclassified_unclassified--122_26-1600x1200.jpg",
    "description": "",
    "thumbUrl": "https://timgsa.182.40.194.50/timg?image&quality=80&size=b9999_10000&sec=1577945612638&di=81a0281095a337037abf85f29929b55f&imgtype=0&src=http%3A%2F%2Fimage5.92bizhi.com%2Funclassified_unclassified--122_26-1600x1200.jpg"
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "发送链接成功",
    "data": {
        "type": null,
        "msgId": 697760503,
        "newMsgId": 181228940242588250,
        "createTime": 1641457185,
        "wcId": "wxid_amdhbnjfj3d"
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