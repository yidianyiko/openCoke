- 修改群名称

## 修改群名称

[!DANGER]修改群名后，如看到群名未更改，是手机缓存问题，可以连续点击进入其他群，在点击进入修改的群，再返回即可看到修改后的群名

请求URL：

- http://域名地址/modifyGroupName

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| chatRoomId | 是 | String | 群号 |
| content | 是 | String | 群名 |

请求参数示例

```
{
    "wId": "349be9b5-8734-45ce-811d-4e10ca568c67",
    "chatRoomId":"24187765053@chatroom",
    "content":"我爱你中国啊啊啊啊啊"
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