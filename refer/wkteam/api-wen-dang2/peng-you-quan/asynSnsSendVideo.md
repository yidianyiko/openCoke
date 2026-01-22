- 异步发送视频朋友圈

## 异步发送视频朋友圈

[!DANGER]

- 微信需在线三天后使用本接口，否则微信团队会提示不可使用副设备发送

简要描述：

- 异步发送视频朋友圈

请求URL：

- http://域名地址/asynSnsSendVideo

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| content | 是 | String | 文本内容 |
| videoPath | 是 | String | 视频链接URL 最大支持20M且30秒内 |
| thumbPath | 是 | String | 视频封面URL 最大支持2M内 |
| groupUser | 否 | String | 对谁可见（传微信号,多个用,分隔） |
| blackList | 否 | String | 对谁不可见（传微信号,多个用.分隔） |

请求参数示例

```
{
    "wId": "0000016e-68f9-99d5-0002-3a1cd9eaaa17",
    "content": "今天还是可以的",
    "videoPath": "https://wkgjonlines.oss-cn-shenzhen.aliyuncs.com/movies/20191113/d7c616569ac342ad1fa8e3301682844e.mp4",
    "thumbPath": "http://cdn.duitang.com/uploads/item/201412/21/20141221161645_2MSeA.jpeg"
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "处理成功",
    "data": {
        "asynId": "04d0af77-3877-4621-85ce-c8bee6a460e4"
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
| asynId | String | 异步发送视频朋友圈asynId，可用此参数获取发送视频朋友圈结果 |