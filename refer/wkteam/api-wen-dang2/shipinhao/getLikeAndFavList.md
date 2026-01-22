- 获取赞和收藏的视频列表

## 获取赞和收藏的视频列表

请求URL：

- http://域名/finder/getLikeAndFavList

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| lastBuffer | 否 | String | 首次传空，后续传接口返回的lastBuffer |
| myUserName | 是 | String | 自己的用户编码（获取个人主页接口返回的userName） |
| myRoleType | 是 | int | 自己的角色类型，根据角色关注（获取个人主页接口返回的roleType） |
| flag | 是 | int | 视频类型，7:全部 1:红心 2:大拇指 4:收藏 |

请求参数示例

```
{
    "wId": "2c7a5bf6-e23d-x-8f03-b90e844b539f",
    "lastBuff": "",
    "myUserName":"v2_060000231003b20faec8cae18cb07ea33b077ba915250774edbea38082ea6b24af229@finder",
    "myRoleType": 3,
    "flag": 7 
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "获取关注列表成功",
    "data": {
        "contactList": [
            {
                "clubInfo": {},
                "spamStatus": 0,
                "liveInfo": {
                    "switchFlag": 53727,
                    "micSetting": {},
                    "anchorStatusFlag": 2048,
                    "lotterySetting": {
                        "attendType": 4,
                        "settingFlag": 0
                    }
                },
                "signature": "",
                "headUrl": "https://wx.qlogo.cn/finderhead/ver_1/XBMFoPXk0XSgBdBoKSNFiaTLrO87hTOrXrAgrPyLaav7djjqvWReQz2T595mBW6ic267eYfibYbcEzAytKD9RrmGPzoBIYrUPubTWwIT4U0CeY/0",
                "authInfo": {},
                "extInfo": {
                    "country": "CN",
                    "province": "Jiangsu",
                    "city": "Nanjing",
                    "sex": 1
                },
                "coverImgUrl": "",
                "extFlag": 262156,
                "followTime": 1718847509,
                "liveCoverImgUrl": "",
                "nickname": "阿星5679",
                "followFlag": 1,
                "liveStatus": 2,
                "username": "v2_060000231003b20faec8c7ea8f1ecbd1c901ef3cb0773696efb506324185fdd53ba44426a8a7@finder",
                "status": 0
            },
            {
                "clubInfo": {},
                "spamStatus": 0,
                "liveInfo": {
                    "switchFlag": 53727,
                    "micSetting": {},
                    "anchorStatusFlag": 2048,
                    "lotterySetting": {
                        "attendType": 4,
                        "settingFlag": 0
                    }
                },
                "signature": "啦啦啦啦啦啦",
                "headUrl": "https://wx.qlogo.cn/finderhead/ver_1/y0XfC6SVbzYVl1SIZt2ZaMbicpXmQqmHPK6oibGpfesFYjVevZOMvkemVWx5YgtUKH3xXNZOoPSztq0Dw23lnF3rBIZNf9S8NsicoEteQNZRqk/0",
                "authInfo": {},
                "extInfo": {
                    "country": "CN",
                    "province": "Jiangsu",
                    "city": "Nanjing",
                    "sex": 1
                },
                "coverImgUrl": "",
                "extFlag": 262156,
                "followTime": 1702883528,
                "liveCoverImgUrl": "",
                "nickname": "爱德华9813",
                "followFlag": 1,
                "liveStatus": 2,
                "username": "v2_060000231003b20faec8c7e08f10c1d4c803ef36b077bc0b9fb41ae2efc82c20ba5fb68f838a@finder",
                "status": 0
            }
        ],
        "lastBuffer": "CK23AhAA",
        "followCount": 2,
        "continueFlag": 0
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