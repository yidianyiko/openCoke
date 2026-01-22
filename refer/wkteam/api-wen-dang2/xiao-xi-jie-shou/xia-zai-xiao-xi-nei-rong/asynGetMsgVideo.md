- 异步下载消息中的视频

## 异步下载消息中的视频

简要描述：

- 异步下载消息中的视频

请求URL：

- http://域名地址/asynGetMsgVideo

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | string | 登录实例标识(包含此参数 所有参数都是从消息回调中取） |
| msgId | 是 | long | 消息id |
| content | 是 | string | 收到的消息的xml数据 |

返回数据：

| 参数名 | 类型 | 说明 |
| code | string | 1000成功，1001失败 |
| msg | string | 反馈信息 |
| data | string |  |
| data.id | string | 异步下载视频id，可用此参数获取下载视频结果 |

请求参数示例

```
{
   "wId": "0000016f-a3f4-7ac2-0001-4686486bb6c6",
   "msgId": 1102684153,
   "content" :"<?xml version=\"1.0\"?><msg><videomsg aeskey=\"cc054b6e3e98fe91a5bb16227de67023\" cdnthumbaeskey=\"cc054b6e3e98fe91a5bb16227de67023\" cdnvideourl=\"304f02010004483046020100020466883f5202032f5081020491eff98c02045e1db76004213439346431383637346131316634356332613338363436613530633439376233320204010400040201000400\" cdnthumburl=\"304f02010004483046020100020466883f5202032f5081020491eff98c02045e1db76004213439346431383637346131316634356332613338363436613530633439376233320204010400040201000400\" length=\"966424\" playlength=\"15\" cdnthumblength=\"5819\" cdnthumbwidth=\"0\" cdnthumbheight=\"0\" fromusername=\"wxid_lr6j4nononb921\" md5=\"5056a23087ce5a8fe97042f0e5f87503\" newmd5=\"8eb2172bf0c03b2bc5af09effcaaba3d\" isad=\"0\" /></msg>"
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "处理成功",
    "data": {
        "id": "6eb5d834-1dfe-47ad-b7a5-b9f2fb60a35a"
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