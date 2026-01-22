- 转发小程序

## 转发小程序

请求URL：

- http://域名地址/sendApplet

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | string | 登录实例标识 |
| wcId | 是 | string | 接收方微信id/群id |
| imgUrl | 是 | string | 小程序封面图(50KB以内的png/jpg) |
| content | 是 | string | 小程序xml内容,(小程序xml需先收集入库，也就是说将想要发送的小程序手动发送给机器人微信，此时消息回调中获取xml内容，xml去掉部分仅截取appmsg开头与结尾的，具体请看请求参数示例,且xml中可以自定义任意参数，例如：携带参数的跳转地址，缩略图等） |  |

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

    "wId": "0000016f-78bd-21c8-0001-29c4d004ae46",
    "wcId": "jack_623555049",
    "imgUrl":"http://photocdn.sohu.com/20120323/Img338614056.jpg",
    "content": "<appmsg appid=\"\" sdkver=\"0\">\n\t\t<title>云铺海购</title>\n\t\t<des>云铺海购</des>\n\t\t<type>33</type>\n\t\t<url>https://mp.weixin.qq.com/mp/waerrpage?appid=wx07af7e375d21a08c&amp;type=upgrade&amp;upgradetype=3#wechat_redirect</url>\n\t\t<appattach>\n\t\t\t<cdnthumburl>3057020100044b30490201000204502c9b9f02032f55f902040ed15eda0204632dc841042461316335306262662d393337322d343361332d383631312d6166613731306362643764300204011400030201000405004c51e500</cdnthumburl>\n\t\t\t<cdnthumbmd5>e1c43f713ebc389dc8f89690aeb7ecb4</cdnthumbmd5>\n\t\t\t<cdnthumblength>58598</cdnthumblength>\n\t\t\t<cdnthumbwidth>720</cdnthumbwidth>\n\t\t\t<cdnthumbheight>576</cdnthumbheight>\n\t\t\t<cdnthumbaeskey>125805800e40722f240220286e3ef74d</cdnthumbaeskey>\n\t\t\t<aeskey>125805800e40722f240220286e3ef74d</aeskey>\n\t\t\t<encryver>0</encryver>\n\t\t\t<filekey>wxid_ctqh94e1ahe722_26_1663944768</filekey>\n\t\t</appattach>\n\t\t<sourceusername>gh_12566478d436@app</sourceusername>\n\t\t<sourcedisplayname>云铺海购</sourcedisplayname>\n\t\t<md5>e1c43f713ebc389dc8f89690aeb7ecb4</md5>\n\t\t<recorditem><![CDATA[(null)]]></recorditem>\n\t\t<weappinfo>\n\t\t\t<username><![CDATA[gh_12566478d436@app]]></username>\n\t\t\t<appid><![CDATA[wx07af7e375d21a08c]]></appid>\n\t\t\t<type>2</type>\n\t\t\t<version>14</version>\n\t\t\t<weappiconurl><![CDATA[http://mmbiz.qpic.cn/mmbiz_png/uLxzSQcibsGzibyibBMLZhib1ick4RhO4ic203iaKMMSL35riafKicdyy8OX0ibjeDrs4Vka2KwTibiaPiaeXBKDQ24pblJO6mg/640?wx_fmt=png&wxfrom=200]]></weappiconurl>\n\t\t\t<pagepath><![CDATA[pages/home/dashboard/index.html?shopAutoEnter=1&is_share=1&share_cmpt=native_wechat&kdt_id=109702811&from_uuid=FgPTe5LTPr00dw21663912217667]]></pagepath>\n\t\t\t<shareId><![CDATA[0_wx07af7e375d21a08c_5a36c4cc14fb8effefecbd92a1f291a6_1663944761_0]]></shareId>\n\t\t\t<appservicetype>0</appservicetype>\n\t\t\t<brandofficialflag>0</brandofficialflag>\n\t\t\t<showRelievedBuyFlag>0</showRelievedBuyFlag>\n\t\t\t<subType>0</subType>\n\t\t\t<isprivatemessage>0</isprivatemessage>\n\t\t</weappinfo>\n\t</appmsg>"
    ...///这个xml图片的缩略图过期  可以调用CDN图片上传接口 自定义替换参数
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