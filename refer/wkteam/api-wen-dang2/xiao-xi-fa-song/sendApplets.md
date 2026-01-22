- 发送小程序

## 发送小程序

请求URL：

- http://域名地址/sendApplets

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | string | 登录实例标识 |
| wcId | 是 | string | 接收方微信id/群id |
| displayName | 是 | string | 小程序的名称，例如：京东 |
| iconUrl | 是 | string | 小程序卡片图标的url(50KB以内的png/jpg) |
| appId | 是 | string | 小程序的appID,例如：wx7c544xxxxxx |
| pagePath | 是 | string | 点击小程序卡片跳转的url |
| thumbUrl | 是 | string | 小程序卡片缩略图的url(50KB以内的png/jpg) |
| title | 是 | string | 标题 |
| userName | 是 | string | 小程序所有人的ID,例如：gh_1c0daexxxx@app |

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

[!DANGER]小提示：

- 参数来源可看消息回调中小程序消息，自定义相关参数

请求参数示例

```
{

    "wId": "0000016f-78bd-21c8-0001-29c4d004ae46",
    "wcId": "filehelper",
      "displayName": "云铺海购",
    "iconUrl": "无用",
    "appId": "wx07af7e375d21a08c",
    "pagePath": "pages/home/dashboard/index.html?shopAutoEnter=1&is_share=1&share_cmpt=native_wechat&kdt_id=109702811&from_uuid=FgPTe5LTPr00dw21663912217667",
    "thumbUrl": "https://pic3.zhimg.com/v2-f73763905eed23308466e441430a43be_r.jpg",
    "title": "云铺海购",
    "userName": "gh_12566478d436@app"

}

```

成功返回示例

```
{
    "code": "1000",
    "message": "发送小程序成功",
    "data": {
        "type": 0,
        "msgId": 697760545,
        "newMsgId": 7645748705605226305,
        "createTime": 1641458149,
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