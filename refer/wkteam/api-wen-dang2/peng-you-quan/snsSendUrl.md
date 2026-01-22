- 发送链接朋友圈消息

## 发送链接朋友圈消息

[!DANGER]

- 微信需在线三天后使用本接口，否则微信团队会提示不可使用副设备发送

简要描述：

- 发送链接朋友圈消息

请求URL：

- http://域名地址/snsSendUrl

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| content | 是 | String | 文本内容 |
| title | 是 | String | 标题 |
| description | 是 | String | 描述 |
| url | 是 | String | url |
| thumbUrl | 是 | String | 缩略图url |
| groupUser | 否 | String | 对谁可见（传微信id,多个用,分隔） |
| blackList | 否 | String | 对谁不可见（传微信id,多个用,分隔） |
| groupUserLabelIds | 否 | String | 对谁可见（传标签id,多个用,分隔） |
| blackListLabelIds | 否 | String | 对谁不可见（传标签id,多个用,分隔） |

请求参数示例

```
{
    "wId": "25dea7a4-ddea-40c6-87ad-3e982e998921",
    "content": "测试",
    "title": "jr加盟湖人",
    "description": "ddd",
    "url": "https://mp.weixin.qq.com/s/cxJ7pLvkRwBV_NUfQxNEjA",
    "thumbUrl": "http://dmjvip.oss-cn-shenzhen.aliyuncs.com/download/dailyimg/20200618155919206.jpg"
}

```

成功返回示例

```
{
    "message": "成功",
    "code": "1000",
    "data": {
        "status": 1,
        "object": {
            "id": "13367129656153944194",
            "userName": "wxid_gia1nwcgpobz22",
            "createTime": 1593486029,
            "objectDesc": "iLen: 2129\nbuffer: \"<TimelineObject><id><![CDATA[13367129656153944194]]></id><username><![CDATA[wxid_gia1nwcgpobz22]]></username><createTime><![CDATA[1593486029]]></createTime><contentDescShowType>0</contentDescShowType><contentDescScene>0</contentDescScene><private><![CDATA[0]]></private><contentDesc><![CDATA[\\346\\265\\213\\350\\257\\225\\345\\223\\210\\345\\223\\210\\345\\223\\210\\345\\223\\210]]></contentDesc><contentattr><![CDATA[0]]></contentattr><sourceUserName></sourceUserName><sourceNickName></sourceNickName><statisticsData></statisticsData><weappInfo><appUserName></appUserName><pagePath></pagePath><version><![CDATA[0]]></version><debugMode><![CDATA[0]]></debugMode><shareActionId></shareActionId><isGame><![CDATA[0]]></isGame><messageExtraData></messageExtraData><subType><![CDATA[0]]></subType></weappInfo><canvasInfoXml></canvasInfoXml><ContentObject><contentStyle><![CDATA[3]]></contentStyle><contentSubStyle><![CDATA[0]]></contentSubStyle><title><![CDATA[jr\\345\\212\\240\\347\\233\\237\\346\\271\\226\\344\\272\\272]]></title><description><![CDATA[ddd]]></description><contentUrl><![CDATA[https://mp.weixin.qq.com/s/cxJ7pLvkRwBV_NUfQxNEjA]]></contentUrl><mediaList><media><id><![CDATA[13367129656558694540]]></id><type><![CDATA[2]]></type><title></title><description></description><private><![CDATA[0]]></private><url type=\\'\\\\&quot;1\\\\&quot;\\'><![CDATA[http://dmjvip.oss-cn-shenzhen.aliyuncs.com/download/dailyimg/20200618155919206.jpg]]></url><thumb type=\\'\\\\&quot;1\\\\&quot;\\'><![CDATA[http://dmjvip.oss-cn-shenzhen.aliyuncs.com/download/dailyimg/20200618155919206.jpg]]></thumb><videoDuration><![CDATA[0.0]]></videoDuration><size height=\\'\\\\&quot;113.0\\\\&quot;\\' width=\\'\\\\&quot;150.0\\\\&quot;\\' totalSize=\\'\\\\&quot;24051.0\\\\&quot;\\'></size></media></mediaList></ContentObject><actionInfo><appMsg><mediaTagName></mediaTagName><messageExt></messageExt><messageAction></messageAction></appMsg></actionInfo><statExtStr></statExtStr><appInfo><id></id></appInfo><location poiClassifyId=\\\"\\\" poiName=\\\"\\\" poiAddress=\\\"\\\" poiClassifyType=\\\"0\\\" city=\\\"\\\"></location><publicUserName></publicUserName><streamvideo><streamvideourl></streamvideourl><streamvideothumburl></streamvideothumburl><streamvideoweburl></streamvideoweburl></streamvideo><showFlag></showFlag></TimelineObject>\"\n"
        }
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
| code | string | 1000成功，1001失败 |
| msg | String | 反馈信息 |
| data |  |
| id | String | ID |
| userName | String | 微信id |
| createTime | String | 发送时间 |
| objectDesc | String | 内容 |