- 获取群成员详情

## 获取群成员详情

简要描述：

- 获取群成员详情

请求URL：

- http://域名/getChatRoomMemberInfo

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| chatRoomId | 是 | String | 群号 |
| userList | 是 | String | 群成员标识PS: 暂不支持多个群成员查询，可间隔调用获取 |

请求参数示例

```
{
    "wId": "4941c159-48dc-4271-b0d0-f94adea39127",
    "chatRoomId":"232323232@chatRoom",
    "userList": "wxid_daydt60mc0ny22"
}

```

成功返回示例

```
{
    "message": "成功",
    "code": "1000",
    "data": [
        {
            "userName": "wxid_daydt6xx1c0ny22",
            "nickName": "北京123",
            "remark": "",
            "signature": "",
            "sex": 0,
            "aliasName": "xxxxxuai0309",
            "country": null,
            "bigHead": "https://t8.182.40.194.50/it/u=1484500186,1503043093&fm=79&app=86&size=h300&n=0&g=4n&f=jpeg?sec=1593075215&t=4d1c7f8cab5417b9ebec450bb180d00e",
            "smallHead": "https://t8.182.40.194.50/it/u=1484500186,1503043093&fm=79&app=86&size=h300&n=0&g=4n&f=jpeg?sec=1593075215&t=4d1c7f8cab5417b9ebec450bb180d00e",
            "labelList": null,
            "v1": "v3_020b3826fd030100000xxx9b4df5b5000000501ea9a3dba12f95f6b60a0536a1adb69d4c980f5186cb7f0dbb8ee9b5f0cdcf4a075737d607e1803aededdd3a719b452a84dbf83c12e07b110dae9260e6ac806c82f3xxx80ad6085660a9@stranger",
            "v2": ""
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
| code | string | 1000成功1001失败 |
| msg | String | 反馈信息 |
| data | JSONObject |
| userName | String | 微信id |
| nickName | String | 昵称 |
| aliasName | String | 微信号 |
| signature | String | 签名 |
| sex | int | 性别 |
| bigHead | String | 大头像 |
| smallHead | String | 小头像 |
| v1 | String | v1 |
| v2 | String | v2 |