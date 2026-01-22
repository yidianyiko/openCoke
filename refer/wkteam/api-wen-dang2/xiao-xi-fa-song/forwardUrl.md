- 转发链接消息

# 转发链接消息

简要描述：

- 根据消息回调收到的xml转发链接消息，适用于同内容大批量发送，可点击此处查看使用方式，第2大类4小节

请求URL：

- http://域名地址/forwardUrl

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | string | 登录实例标识 |
| wcId | 是 | string | 接收人微信id/群id |
| content | 是 | string | xml文件内容 |

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
   "wId": "0000016f-a805-4715-0001-848f9a297a40",
   "wcId":"jack_623555049",
   "content": "<?xml version=\"1.0\"?>\n<msg>\n\t<appmsg appid=\"\" sdkver=\"0\">\n\t\t<title>理想汽车正式登陆纳斯达克！</title>\n\t\t<des>7月30日，理想汽车正式在美国纳斯达克证券市场正式挂牌上市，股票代码为“LI”，发行价格为每股11.5美元。</des>\n\t\t<action />\n\t\t<type>5</type>\n\t\t<showtype>0</showtype>\n\t\t<soundtype>0</soundtype>\n\t\t<mediatagname />\n\t\t<messageext />\n\t\t<messageaction />\n\t\t<content />\n\t\t<contentattr>0</contentattr>\n\t\t<url>http://mp.weixin.qq.com/s?__biz=MzU0Mjk1MDk4MA==&amp;mid=2247489268&amp;idx=1&amp;sn=b9df468408299b16ea55b804f8eaac6f&amp;chksm=fb1385dfcc640cc90de251b2d641739fe91278c6d6c3a94239cadfe0f5f1146bdf283d7b73a6&amp;mpshare=1&amp;scene=2&amp;srcid=0730zRNXTUJqhf7Fztpamu6n&amp;sharer_sharetime=1596158677187&amp;sharer_shareid=b5d32fcdbf6f6bd1700daee19cead97b#rd</url>\n\t\t<lowurl />\n\t\t<dataurl />\n\t\t<lowdataurl />\n\t\t<songalbumurl />\n\t\t<songlyric />\n\t\t<appattach>\n\t\t\t<totallen>0</totallen>\n\t\t\t<attachid />\n\t\t\t<emoticonmd5></emoticonmd5>\n\t\t\t<fileext />\n\t\t\t<cdnthumburl>30570201000450304e0201000204502c9b9f02032f55f90204a40260b402045f2379650429777875706c6f61645f777869645f796c7874666c636730703862323237395f313539363136303335370204010400030201000400</cdnthumburl>\n\t\t\t<cdnthumbmd5>51f22eeff56ff76a7cab2bf177ef6c1a</cdnthumbmd5>\n\t\t\t<cdnthumblength>25332</cdnthumblength>\n\t\t\t<cdnthumbwidth>150</cdnthumbwidth>\n\t\t\t<cdnthumbheight>150</cdnthumbheight>\n\t\t\t<cdnthumbaeskey>99e7fd1d7d33dba159edfa52607645c3</cdnthumbaeskey>\n\t\t\t<aeskey>99e7fd1d7d33dba159edfa52607645c3</aeskey>\n\t\t\t<encryver>0</encryver>\n\t\t\t<filekey>wxid_ylxtflcg0p8b2279_1596160357</filekey>\n\t\t</appattach>\n\t\t<extinfo />\n\t\t<sourceusername>gh_89701dbd6858</sourceusername>\n\t\t<sourcedisplayname>理想汽车</sourcedisplayname>\n\t\t<thumburl />\n\t\t<md5 />\n\t\t<statextstr />\n\t\t<directshare>0</directshare>\n\t\t<mmreadershare>\n\t\t\t<itemshowtype>0</itemshowtype>\n\t\t\t<nativepage>0</nativepage>\n\t\t\t<pubtime>0</pubtime>\n\t\t\t<duration>0</duration>\n\t\t\t<width>0</width>\n\t\t\t<height>0</height>\n\t\t\t<vid />\n\t\t\t<funcflag>0</funcflag>\n\t\t\t<ispaysubscribe>0</ispaysubscribe>\n\t\t</mmreadershare>\n\t</appmsg>\n\t<fromusername>wxid_i6qsbbjenjuj22</fromusername>\n\t<scene>0</scene>\n\t<appinfo>\n\t\t<version>1</version>\n\t\t<appname />\n\t</appinfo>\n\t<commenturl />\n</msg>\n"
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "转发文件成功",
    "data": {
        "type": 6,
        "msgId": 697760535,
        "newMsgId": 6957007917217750754,
        "createTime": 1641457929,
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