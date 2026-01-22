- 下载文件

# 下载文件

简要描述：

- 下载消息中的文件

请求URL：

- http://域名地址/getMsgFile

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | string | 登录实例标识包含此参数 所有参数都是从消息回调中取） |
| msgId | 是 | long | 消息id |
| content | 是 | string | 收到的消息的xml数据 |

返回数据：

| 参数名 | 类型 | 说明 |
| code | string | 1000成功，1001失败 |
| msg | string | 反馈信息 |

请求参数示例

```
{
   "wId": "0000016f-a3f4-7ac2-0001-4686486bb6c6",
   "msgId": 1102684150,
   "content": "<?xml version=\"1.0\"?><msg><appmsg appid=\"wx6618f1cfc6c132f8\" sdkver=\"0\"><title>下载文件.txt</title><des /><action>view</action><type>6</type><showtype>0</showtype><content /><url /><dataurl /><lowurl /><lowdataurl /><recorditem><![CDATA[]]></recorditem><thumburl /><messageaction /><extinfo /><sourceusername /><sourcedisplayname /><commenturl /><appattach><totallen>6</totallen><attachid>@cdn_304e02010004473045020100020466883f5202032f55f90204260260b402045e1db470042036626464393436656537643431613836623065383665373034396538646566630204010400050201000400_17dd9d048f84c77db909b2161d6dbb09_1</attachid><emoticonmd5></emoticonmd5><fileext>txt</fileext><cdnattachurl>304e02010004473045020100020466883f5202032f55f90204260260b402045e1db470042036626464393436656537643431613836623065383665373034396538646566630204010400050201000400</cdnattachurl><aeskey>17dd9d048f84c77db909b2161d6dbb09</aeskey><encryver>1</encryver></appattach><weappinfo><pagepath /><username /><appid /><appservicetype>0</appservicetype></weappinfo><websearch /><md5>8c8fa3529ee34d4e69a0baafb7069da3</md5></appmsg><fromusername>wxid_lr6j4nononb921</fromusername><scene>0</scene><appinfo><version>7</version><appname>微信电脑版</appname></appinfo><commenturl /></msg>"
}

```

成功返回示例

```
{
    "message": "成功",
    "code": "1000",
    "data": {
        "url": "下载文件.txt"
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