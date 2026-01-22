- 获取群成员

## 获取群成员

简要描述：

- 获取群成员

请求URL：

- http://域名地址/getChatRoomMember

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
            "chatRoomId": "23282491030@chatroom",
            "userName": "wxid_wl9qchkanp9u22",
            "nickName": "E云通知小助手（机器人）",
            "chatRoomOwner": null,
            "bigHeadImgUrl": "http://wx.qlogo.cn/mmhead/ver_1/DEjvrt3YDnqggwzHj2LQTwY3K1y6TWVC615azPYb3RSWgeMvE5ny1kYQSBoNLgCicRMGa9LRp9dQJy2HHurNSYqqZNf5NTxicDMTNdjL3SrAI/0",
            "smallHeadImgUrl": "http://wx.qlogo.cn/mmhead/ver_1/DEjvrt3YDnqggwzHj2LQTwY3K1y6TWVC615azPYb3RSWgeMvE5ny1kYQSBoNLgCicRMGa9LRp9dQJy2HHurNSYqqZNf5NTxicDMTNdjL3SrAI/132",
            "v1": null,
            "memberCount": 0,
            "displayName": "",
            "chatRoomMembers": null
        },
        {
            "chatRoomId": "23282491030@chatroom",
            "userName": "wxid_i6qsbbjenjuj22",
            "nickName": "E云Team_Mr Li",
            "chatRoomOwner": null,
            "bigHeadImgUrl": "http://wx.qlogo.cn/mmhead/ver_1/licI98sKzmtB0BWmDGvVaqcvCmDMMbLsGku18zHpxoxYibXH2QhZibTIjOPhzlpAkQic8Tlhdk4lCAIlE0twxQnqng4M4CKcV3ps52wOfcMHemo/0",
            "smallHeadImgUrl": "http://wx.qlogo.cn/mmhead/ver_1/licI98sKzmtB0BWmDGvVaqcvCmDMMbLsGku18zHpxoxYibXH2QhZibTIjOPhzlpAkQic8Tlhdk4lCAIlE0twxQnqng4M4CKcV3ps52wOfcMHemo/132",
            "v1": null,
            "memberCount": 0,
            "displayName": "",
            "chatRoomMembers": null
        },
        {
            "chatRoomId": "23282491030@chatroom",
            "userName": "wxid_ew6i9qdxlinu12",
            "nickName": "E云客服-可可(工作日09:00-18:00)",
            "chatRoomOwner": null,
            "bigHeadImgUrl": "http://wx.qlogo.cn/mmhead/ver_1/avZnWvIiaulTibWZDqvjic9zNsW9F5n5GN5AoNIian9U1w86TAwicqjMa3esFLOzFfUNI4icCeziauRhOEOxicadyarDmQqf679VsUiaxhawibia9wficSE/0",
            "smallHeadImgUrl": "http://wx.qlogo.cn/mmhead/ver_1/avZnWvIiaulTibWZDqvjic9zNsW9F5n5GN5AoNIian9U1w86TAwicqjMa3esFLOzFfUNI4icCeziauRhOEOxicadyarDmQqf679VsUiaxhawibia9wficSE/132",
            "v1": null,
            "memberCount": 0,
            "displayName": "",
            "chatRoomMembers": null
        },
        {
            "chatRoomId": "23282491030@chatroom",
            "userName": "wxid_ylxtflcg0p8b22",
            "nickName": "售前客服-小诺 (工作日9:00-18:00)",
            "chatRoomOwner": null,
            "bigHeadImgUrl": "http://wx.qlogo.cn/mmhead/ver_1/5Aiaticzwasiac9drMyibhHrDRIsadlS4sKWp4ia3QdaKfAe6RcOhHjTtk0qzJTEQagNTM1R4WZVvAvqVMn02DGrIOEj2ZQwDD0HzHyq95Nc5zlw/0",
            "smallHeadImgUrl": "http://wx.qlogo.cn/mmhead/ver_1/5Aiaticzwasiac9drMyibhHrDRIsadlS4sKWp4ia3QdaKfAe6RcOhHjTtk0qzJTEQagNTM1R4WZVvAvqVMn02DGrIOEj2ZQwDD0HzHyq95Nc5zlw/132",
            "v1": null,
            "memberCount": 0,
            "displayName": "啦啦啦",
            "chatRoomMembers": null
        },
        {
            "chatRoomId": "23282491030@chatroom",
            "userName": "wxid_nqo37ves8w5t22",
            "nickName": "追风少年666",
            "chatRoomOwner": null,
            "bigHeadImgUrl": "http://wx.qlogo.cn/mmhead/ver_1/G9GD3GENzHvn9hEiaw0JJzwGYD2jIiczflo0DHcVTXuqIiavsB9W51Z3GTv3RqkdOY3xyhMicAicOZDSqBDOAelfD4AjaKo4Q5EsMa7MIgGbj8IY/0",
            "smallHeadImgUrl": "http://wx.qlogo.cn/mmhead/ver_1/G9GD3GENzHvn9hEiaw0JJzwGYD2jIiczflo0DHcVTXuqIiavsB9W51Z3GTv3RqkdOY3xyhMicAicOZDSqBDOAelfD4AjaKo4Q5EsMa7MIgGbj8IY/132",
            "v1": null,
            "memberCount": 0,
            "displayName": "",
            "chatRoomMembers": null
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
| data | JSONObject |  |
| chatRoomId | String | 群号 |
| userName | String | 群成员微信号（假如需要手机上显示的微信号或更详细的信息，则需要再调用获取群成员详情接口获取） |
| nickName | String | 群成员默认昵称 |
| displayName | String | 群成员修改后的昵称 |
| bigHeadImgUrl | String | 大头像 |
| smallHeadImgUrl | String | 小头像 |
| chatRoomMemberFlag | int |  |
| inviterUserName | String | 邀请人微信号（仅有群主和管理可以看到） |