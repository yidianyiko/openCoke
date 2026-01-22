- 关注

## 关注

请求URL：

- http://域名/finderFollow

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| userName | 是 | String | 视频号用户的编码（搜索接口返回的userName） |
| meUserName | 是 | String | 自己的用户编码（获取个人主页接口返回的userName） |
| meRoleType | 是 | int | 自己的角色类型，根据角色关注（获取个人主页接口返回的roleType） |
| type | 是 | int | 操作类型1:关注2:取消关注 |

请求参数示例

```
{
    "wId": "{{wId}}",
    "meUserName": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx@finder",
    "userName": "v2_060000231003b20faec8c6e78010c3d4c605eb3cb077f16e37c172145877400390b1170a0299@finder",
    "meRoleType": 3,
    "type": 1
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "处理成功",
    "data": {
        "userName": "v2_060000231003b20faec8c6e78010c3d4c605eb3cb077f16e37c172145877400390b1170a0299@finder",
        "nickName": "中国日报",
        "headUrl": "https://wx.qlogo.cn/finderhead/ver_1/BuStUlORBaLHz4E85tq01bL7icWQJ25baldDJ8Ky5114GtJXVvibDjpZuPQrfALbF1EZU5vzAnS0GnObG4whzdBmbWyKHiblHib6RC5JaGdj0FM/0",
        "signature": "",
        "authInfo": {
            "authIconType": 2,
            "authProfession": "中国日报社",
            "detailLink": "pages/index/index.html?showdetail=true&username=v2_060000231003b20faec8c6e78010c3d4c605eb3cb077f16e37c172145877400390b1170a0299@finder",
            "appName": "gh_4ee148a6ecaa@app"
        },
        "extInfo": {
            "country": "CN",
            "province": "",
            "city": "",
            "sex": null
        },
        "userMode": null,
        "bindInfo": "CAESwwIKwAIKD2doXzM3MDdkOTU0MWMzZhIM5Lit5Zu95pel5oqlGpQBaHR0cHM6Ly93eC5xbG9nby5jbi9tbWhlYWQvdmVyXzEvQnVTdFVsT1JCYUxIejRFODV0cTAxYzQ1ZVEybjhpY3MwQVZKNFM5SHd5R3lVQ1pyanlLRWliZ3ExMVhkcUxHZmtpYUh3OXRpY0tRdEFjZ1Nsc3FaT1VLRGF2TUNQZlR4cmd6bmIyR2hLWTlzTm53LzEzMjKHAQgCEoIBaHR0cHM6Ly9kbGRpcjF2Ni5xcS5jb20vd2VpeGluL2NoZWNrcmVzdXBkYXRlL2ljb25zX2ZpbGxlZF9jaGFubmVsc19hdXRoZW50aWNhdGlvbl9lbnRlcnByaXNlX2EyNjU4MDMyMzY4MjQ1NjM5ZTY2NmZiMTE1MzNhNjAwLnBuZw=="
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
| code | String | 1000成功1001失败 |
| msg | String | 反馈信息 |
| data | JSONObject |