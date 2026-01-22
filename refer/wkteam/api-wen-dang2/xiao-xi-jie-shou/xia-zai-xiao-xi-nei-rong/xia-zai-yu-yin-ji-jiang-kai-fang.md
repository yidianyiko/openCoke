- 下载消息中的语音

## 下载消息中的语音

[!DANGER]

- 下载成功后，如需要 silk 格式转换成MP3等格式，可参考此类库自行转换：https://github.com/kn007/silk-v3-decoder/

简要描述：

- 下载消息中的语音

请求URL：

- http://域名地址/getMsgVoice

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | string | 登录实例标识包含此参数 所有参数都是从消息回调中取） |
| msgId | 是 | long | 消息id |
| length | 是 | int | 语音长度（xml数据中的length字段） |
| bufId | 是 | string | xml中返回的bufId字段值 |
| fromUser | 是 | string | 发送者 |

返回数据：

| 参数名 | 类型 | 说明 |
| code | string | 1000成功，1001失败 |
| msg | string | 反馈信息 |

请求参数示例

```
{
    "wId": "24a929b2-016d-4932-b93f-ff1b0a800305",
    "msgId": 1114311129,
    "fromUser": "zhongweiyu789",
    "bufId": "289139440622895483",
    "length":3227
}

```

成功返回示例

```
{
    "message": "成功",
    "code": "1000",
    "data": {
        "url": "https://weikong-1301028514.cos.ap-shanghai.myqcloud.com//msgImg/e2045467-b1ac-4b3c-89f8-62ab2b3a2284-1591351192235-300000.silk"
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