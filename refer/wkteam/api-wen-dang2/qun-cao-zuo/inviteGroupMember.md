- 邀请群成员（40人以上）

# 邀请群成员（40人以上）

[!DANGER]

- 群如果开启了群聊邀请确认，本接口将失效，则直接使用邀人入群验证接口
- 群人数在40以上且未开启群聊邀请确认，需用本接口以发送卡片形式邀请群成员，40人以下请调用添加群成员接口

请求URL：

- http://域名地址/inviteChatRoomMember

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | string | 登录实例标识 |
| chatRoomId | 是 | String | 群号 |
| userList | 是 | String | 群成员微信id，多个已 "," 分割 |

返回数据：

| 参数名 | 类型 | 说明 |
| code | string | 1000成功，1001失败 |
| msg | string | 反馈信息 |

请求参数示例

```
{
    "wId": "349be9b5-8734-45ce-811d-4e10ca568c67",
    "chatRoomId":"24187765053@chatroom",
    "userList":"wxid_ew6i9qdxlinu12,wxid_nqo37ves8w5t22"
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