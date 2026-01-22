- 获取群信息

## 获取群信息

简要描述：

- 获取群信息

请求URL：

- http://域名地址/getChatRoomInfo

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| chatRoomId | 是 | String | 群号 |

请求参数示例

```
{
    "wId": "349be9b5-8734-45ce-811d-4e10ca568c67",
    "chatRoomId": "24343869723@chatroom"
}

```

成功返回示例

```
{
    "message": "成功",
    "code": "1000",
    "data": [
        {
            "chatRoomId": "24343869723@chatroom",
            "userName": null,
            "nickName": "",
            "chatRoomOwner": "wxid_ylxtflcg0p8b22",
            "bigHeadImgUrl": null,
            "smallHeadImgUrl": "http://wx.qlogo.cn/mmcrhead/S44kIgicdUQ1LwXCuMlDEnV37pDE2RNYOq5ic7GpZR6icDPT1UvIh7iaKh7rKZMicatXKuvB9J0gIDGVDwKTpeBMyLpoCd3FEhNGic/0",
            "v1": "v1_f4ef1dde421ba4039ee0e7a2dcd555fc7a18bcb3b77face81f425e5ec66e8cab814857df2124c60cc144df1ecc83a096@stranger",
            "memberCount": 3,
            "chatRoomMembers": [
                {
                    "userName": "wxid_wl9qchkanp9u22",
                    "nikeName": "E云通知小助手（机器人）",
                    "inviterUserName": "wxid_ylxtflcg0p8b22"
                },
                {
                    "userName": "wxid_i6qsbbjenjuj22",
                    "nikeName": "E云Team_Mr Li",
                    "inviterUserName": "wxid_ylxtflcg0p8b22"
                },
                {
                    "userName": "wxid_ylxtflcg0p8b22",
                    "nikeName": "售前客服-小诺 (工作日9:00-18:00)",
                    "inviterUserName": ""
                }
            ]
        }
    ]
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
| data | JSONArray |  |
| chatRoomId | String | 群号 |
| nickName | String | 群名称 |
| chatRoomOwner | String | 群主 |
| bigHeadImgUrl | String | 大头像 |
| smallHeadImgUrl | String | 小头像 |
| v1 | String | 群v1 |
| memberCount | int | 群成员数 |
| userName | String | 群成员微信号 |
| nickName | String | 群成员昵称 |
| isManage | boolean | 是否是管理员 |
| inviterUserName | String | 邀请人微信号（仅有群主和管理可以看到） |