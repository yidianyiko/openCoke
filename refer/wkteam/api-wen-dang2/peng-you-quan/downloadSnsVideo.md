- 下载朋友圈视频

## 下载朋友圈视频

简要描述：

- 下载朋友圈视频

请求URL：

- http://域名地址/downloadSnsVideo

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| content | 是 | String | 通过获取某条朋友圈详细内容接口[/getSnsObject]返回的xml |

请求参数示例

```
{
     "wId": "b7ad08a6-77c2-4ad6-894a-29993b84c0e4",
     "content": "<TimelineObject><id><![CDATA[14038975351875178589]]></id><username><![CDATA[wxid_xupxubvp9l0322]]></username><createTime><![CDATA[1673576277]]></createTime><contentDescShowType>0</contentDescShowType><contentDescScene>0</contentDescScene><private><![CDATA[0]]></private><contentDesc><![CDATA[牛初乳，\n我只推荐优乐彤。\n配料表非常干净，\n什么都不添加。\n纯的牛初乳[强][强][强]\n只有优乐彤。\n​]]></contentDesc><contentattr><![CDATA[0]]></contentattr><sourceUserName></sourceUserName><sourceNickName></sourceNickName><statisticsData></statisticsData><weappInfo><appUserName></appUserName><pagePath></pagePath><version><![CDATA[0]]></version><debugMode><![CDATA[0]]></debugMode><shareActionId></shareActionId><isGame><![CDATA[0]]></isGame><messageExtraData></messageExtraData><subType><![CDATA[0]]></subType><preloadResources></preloadResources></weappInfo><canvasInfoXml></canvasInfoXml><ContentObject><contentStyle><![CDATA[15]]></contentStyle><contentSubStyle><![CDATA[0]]></contentSubStyle><title>微信小视频</title><description></description><contentUrl>https://support.weixin.qq.com/cgi-bin/mmsupport-bin/readtemplate?t=page/common_page__upgrade&amp;v=1</contentUrl><mediaList><media><id><![CDATA[14038975352558194743]]></id><type><![CDATA[6]]></type><title><![CDATA[牛初乳，\n我只推荐优乐彤。\n配料表非常干净，\n什么都不添加。\n纯的牛初乳[强][强][强]\n只有优乐彤。\n​]]></title><description><![CDATA[牛初乳，\n我只推荐优乐彤。\n配料表非常干净，\n什么都不添加。\n纯的牛初乳[强][强][强]\n只有优乐彤。\n​]]></description><private><![CDATA[0]]></private><url videomd5=\"6996ba1ff53f976ae5b7da32f1d7a322\" type=\"1\" md5=\"4b9d4d9724363355b713bfc0af924e84\"><![CDATA[http://shzjwxsns.video.qq.com/102/20202/snsvideodownload?filekey=30340201010420301e0201660402534804104b9d4d9724363355b713bfc0af924e8402030f1f54040d00000004627466730000000132&hy=SH&storeid=563c0bf5400001c5a163c605c0000006600004eea534823fe7b01e64626bce&dotrans=9&ef=30_0&bizid=1023&ilogo=2&dur=7&sid=171]]></url><thumb type=\"1\"><![CDATA[http://vweixinthumb.tc.qq.com/150/20250/snsvideodownload?filekey=30350201010421301f02020096040253480410ed875ce3adf71ceab81ff6d9b72d17b7020301851e040d00000004627466730000000132&hy=SH&storeid=563c0bf5400001370163c605c0000009600004f1a5348240348e0b647aff0d&bizid=1023]]></thumb><videoDuration><![CDATA[7.241]]></videoDuration><size totalSize=\"99614.0\" width=\"1080\" height=\"1920\"></size><VideoColdDLRule><All>CAISBAgWEAEoAjAc</All></VideoColdDLRule></media></mediaList></ContentObject><actionInfo><appMsg><mediaTagName></mediaTagName><messageExt></messageExt><messageAction></messageAction></appMsg></actionInfo><appInfo><id></id></appInfo><location poiClassifyId=\"\" poiName=\"\" poiAddress=\"\" poiClassifyType=\"0\" city=\"\"></location><publicUserName></publicUserName><streamvideo><streamvideourl></streamvideourl><streamvideothumburl></streamvideothumburl><streamvideoweburl></streamvideoweburl></streamvideo></TimelineObject>"
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "下载朋友圈视频成功",
    "data": {
        "videoUrl": "http://oos-sccd.ctyunapi.cn/20230116/478bbcfd-169a-4cfc-b768-f51f24f442fb.mp4?AWSAccessKeyId=e14b8966201775518bce&Expires=1674483076&Signature=dqPDwjl4mq6RvPsPuFdWXJOQRf0%3D"
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
| message | String | 反馈信息 |