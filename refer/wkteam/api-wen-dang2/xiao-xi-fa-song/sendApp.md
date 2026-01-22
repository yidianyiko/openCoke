- 发送APP类消息

## 发送APP类消息

[!DANGER]和转发小程序是同一个接口，此接口可发各种类型消息，例如：引用消息，短视频，直播，音乐，第三方APP等（只要消息回调的xml中包含appmsg的消息都可发送）

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
| content | 是 | string | 消息xml回调内容,(此回调的XML需要去掉部分，截取appmsg开头的，具体请看请求参数示例） |  |

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
    "content": "<appmsg appid=\"\" sdkver=\"0\">\n\t\t<title>首页</title>\n\t\t<des />\n\t\t<username />\n\t\t<action>view</action>\n\t\t<type>33</type>\n\t\t<showtype>0</showtype>\n\t\t<content />\n\t\t<url>https://mp.weixin.qq.com/mp/waerrpage?appid=wx9c4062d486855e2f&amp;type=upgrade&amp;upgradetype=3#wechat_redirect</url>\n\t\t<lowurl />\n\t\t<dataurl />\n\t\t<lowdataurl />\n\t\t<contentattr>0</contentattr>\n\t\t<streamvideo>\n\t\t\t<streamvideourl />\n\t\t\t<streamvideototaltime>0</streamvideototaltime>\n\t\t\t<streamvideotitle />\n\t\t\t<streamvideowording />\n\t\t\t<streamvideoweburl />\n\t\t\t<streamvideothumburl />\n\t\t\t<streamvideoaduxinfo />\n\t\t\t<streamvideopublishid />\n\t\t</streamvideo>\n\t\t<canvasPageItem>\n\t\t\t<canvasPageXml><![CDATA[]]></canvasPageXml>\n\t\t</canvasPageItem>\n\t\t<appattach>\n\t\t\t<attachid />\n\t\t\t<cdnthumburl>305c0201000455305302010002042aaae40702032f55f902048e0260b402045ed89962042e6175706170706d73675f333731636636306138623165316663615f313539313235333334353838385f32303838300204010400030201000400</cdnthumburl>\n\t\t\t<cdnthumbmd5>0d249c2dd3b3296a4aea2ac0fbeb865f</cdnthumbmd5>\n\t\t\t<cdnthumblength>72340</cdnthumblength>\n\t\t\t<cdnthumbheight>576</cdnthumbheight>\n\t\t\t<cdnthumbwidth>720</cdnthumbwidth>\n\t\t\t<cdnthumbaeskey>c1ce6b862ceab481955de4cbde33fffc</cdnthumbaeskey>\n\t\t\t<aeskey>c1ce6b862ceab481955de4cbde33fffc</aeskey>\n\t\t\t<encryver>1</encryver>\n\t\t\t<fileext />\n\t\t\t<islargefilemsg>0</islargefilemsg>\n\t\t</appattach>\n\t\t<extinfo />\n\t\t<androidsource>3</androidsource>\n\t\t<thumburl />\n\t\t<mediatagname />\n\t\t<messageaction><![CDATA[]]></messageaction>\n\t\t<messageext><![CDATA[]]></messageext>\n\t\t<emoticongift>\n\t\t\t<packageflag>0</packageflag>\n\t\t\t<packageid />\n\t\t</emoticongift>\n\t\t<emoticonshared>\n\t\t\t<packageflag>0</packageflag>\n\t\t\t<packageid />\n\t\t</emoticonshared>\n\t\t<designershared>\n\t\t\t<designeruin>0</designeruin>\n\t\t\t<designername>null</designername>\n\t\t\t<designerrediretcturl>null</designerrediretcturl>\n\t\t</designershared>\n\t\t<emotionpageshared>\n\t\t\t<tid>0</tid>\n\t\t\t<title>null</title>\n\t\t\t<desc>null</desc>\n\t\t\t<iconUrl>null</iconUrl>\n\t\t\t<secondUrl />\n\t\t\t<pageType>0</pageType>\n\t\t</emotionpageshared>\n\t\t<webviewshared>\n\t\t\t<shareUrlOriginal />\n\t\t\t<shareUrlOpen />\n\t\t\t<jsAppId />\n\t\t\t<publisherId />\n\t\t</webviewshared>\n\t\t<template_id />\n\t\t<md5>0d249c2dd3b3296a4aea2ac0fbeb865f</md5>\n\t\t<weappinfo>\n\t\t\t<pagepath><![CDATA[pages/venue/list.html]]></pagepath>\n\t\t\t<username>gh_6c471f8ef617@app</username>\n\t\t\t<appid>wx9c4062d486855e2f</appid>\n\t\t\t<version>198</version>\n\t\t\t<type>2</type>\n\t\t\t<weappiconurl><![CDATA[http://wx.qlogo.cn/mmhead/Q3auHgzwzM5Rz1QFH4Wpx2ibOTJGgLA9ovlIsFkPszXW4GEIPHkf3ibg/96]]></weappiconurl>\n\t\t\t<shareId><![CDATA[1_wx9c4062d486855e2f_574177060_1591252418_0]]></shareId>\n\t\t\t<appservicetype>0</appservicetype>\n\t\t\t<videopageinfo>\n\t\t\t\t<thumbwidth>720</thumbwidth>\n\t\t\t\t<thumbheight>576</thumbheight>\n\t\t\t\t<fromopensdk>0</fromopensdk>\n\t\t\t</videopageinfo>\n\t\t</weappinfo>\n\t\t<statextstr />\n\t\t<finderFeed>\n\t\t\t<objectId>null</objectId>\n\t\t\t<objectNonceId>null</objectNonceId>\n\t\t\t<feedType>0</feedType>\n\t\t\t<nickname />\n\t\t\t<avatar><![CDATA[null]]></avatar>\n\t\t\t<desc />\n\t\t\t<mediaCount>0</mediaCount>\n\t\t\t<mediaList />\n\t\t</finderFeed>\n\t\t<findernamecard>\n\t\t\t<username />\n\t\t\t<avatar><![CDATA[]]></avatar>\n\t\t\t<nickname />\n\t\t\t<auth_job />\n\t\t\t<auth_icon>0</auth_icon>\n\t\t</findernamecard>\n\t\t<finderTopic>\n\t\t\t<topic />\n\t\t\t<topicType>-1</topicType>\n\t\t\t<iconUrl><![CDATA[]]></iconUrl>\n\t\t\t<desc />\n\t\t\t<location>\n\t\t\t\t<poiClassifyId />\n\t\t\t\t<longitude>0.0</longitude>\n\t\t\t\t<latitude>0.0</latitude>\n\t\t\t</location>\n\t\t</finderTopic>\n\t\t<finderEndorsement>\n\t\t\t<scene><![CDATA[0]]></scene>\n\t\t</finderEndorsement>\n\t\t<directshare>0</directshare>\n\t\t<websearch />\n\t</appmsg>"
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "发送成功",
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