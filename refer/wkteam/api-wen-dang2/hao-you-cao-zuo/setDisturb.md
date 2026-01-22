- 设置聊天免打扰

## 设置聊天免打扰

[!DANGER]设置成功后，效果即刻生效，但设置消息免打扰开关因手机缓存问题，可能会有延迟展示，实际不影响效果，可等待1min后杀掉后台重新进入，设置消息免打扰开关才会同步正常

简要描述：

- 设置群/好友的消息免打扰作用

请求URL：

- http://域名/setDisturb

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| chatRoomId | 是 | String | 好友id/群id |
| type | 是 | int | 0：开启 1：关闭 |

请求参数示例

```
{
    "wId": "xxxxxx",
    "chatRoomId": "24608539283@chatroom",
    "type": 0
}

```

成功返回示例

```
{
    "message": "成功",
    "code": "1000",
    "data": null
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
| code | String | 1000成功1001失败 |
| msg | String | 反馈信息 |
| data | JSONObject |