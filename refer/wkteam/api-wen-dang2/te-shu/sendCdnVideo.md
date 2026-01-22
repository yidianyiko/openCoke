- CDN视频上传

# CDN视频上传

简要描述：

- 视频上传接口，主要应用于多微信发同内容场景，动态组装转发接口xml发送

请求URL：

- http://域名地址/sendCdnVideo

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | string | 登录实例标识 |
| path | 是 | string | 视频url链接 |
| thumbPath | 是 | string | 图片url链接 |

返回数据：

| 参数名 | 类型 | 说明 |
| code | string | 1000成功，1001失败 |
| msg | string | 反馈信息 |
| cdnUrl | string | 视频cdn信息 |
| aesKey | string | 视频key信息 |
| length | string | 视频长度 |

请求参数示例

```
{
    "wId": "xxxxx",
    "path": "https://img.xingkonglian.net/img/1434818025755774976.mp4",
    "thumbPath": "https://img.xingkonglian.net/img/1434770921234632704.png"
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "发送视频消息成功",
    "data": {
        "cdnUrl": "30670201000460305e02010002041b9042eb02033d14b90204fdb2120e020461554e300439777875706c6f61645f5f313633323938303532375f63396333393539312d326639652d346631352d386131662d6166323265343962643130640204011800040201000400",
        "aesKey": "1a8e3941e3cc233e6f151430088eec6e",
        "length": 3124240
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