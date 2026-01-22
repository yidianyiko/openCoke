- 获取异步下载视频消息结果

## 获取异步下载视频消息结果

简要描述：

- 调用异步下载视频接口后可调用本接口获取下载结果，建议每间隔两秒获取一次，或可通过回调消息获取。

请求URL：

- http://域名地址/getMsgVideoRes

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| id | 是 | string | 异步下载视频接口返回的id |

返回数据：

| 参数名 | 类型 | 说明 |
| code | string | 1000成功，1001失败 |
| msg | string | 反馈信息 |
| data | string | 下载结果 |

请求参数示例

```
{
    "id": "6eb5d834-1dfe-47ad-b7a5-b9f2fb60a35a"
}

```

成功返回示例

- data.url：下载成功后的视频地址
- data.type：0：下载中1：下载完成2：下载失败
- 0：下载中
- 1：下载完成
- 2：下载失败
- data.des：描述
- data.id：id

```
{
    "code": "1000",
    "message": "处理成功",
    "data": {
        "url": "http://xxxxxx/20220105/wxid_phyyedw9xap22/f0aa717e-4c34-4185-a420-c831fa40be94.mp4?Expires=1735973855&OSSAccessKeyId=LTAI4G5VB9BMxMDV14c6USjt&Signature=mC8wNsED7qaNGVXL6h1e0ZY4WXE%3D",
        "type": 1,
        "des": null,
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