- 获取发送视频朋友圈结果

## 获取发送视频朋友圈结果

简要描述：

- 获取发送视频朋友圈结果
- 调用异步发送视频朋友圈后可调用本接口获取发送结果，建议每间隔两秒获取一次，或可通过回调消息获取。

请求URL：

- http://域名地址/getAsynSnsSendVideoRes

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| asynId | 是 | String | 异步发送视频朋友圈返回的asynId |

请求参数示例

```
{
    "asynId": "04d0af77-3877-4621-85ce-c8bee6a460e4"
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "处理成功",
    "data": {
        "asynId": "04d0af77-3877-4621-85ce-c8bee6a460e4",
        "type": 1,
        "id": "13768766054025736468",
        "userName": "wxid_phyyedw9xap22",
        "createTime": 1641364819,
        "objectDesc": "今天还是可以的",
        "des": null
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
| data |  |  |
| data.asynId | String | 异步发送视频朋友圈asynId |
| data.type | int | 发送状态。0：发送中、1：发送完成、2：发送失败 |
| data.id | string | 朋友圈id |
| data.userName | string | 发送微信id |
| data.createTime | long | 发送时间 |
| data.objectDesc | string | 朋友圈文字 |
| data.des | string | 描述 |