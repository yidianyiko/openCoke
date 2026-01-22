- 消息列表

## 消息列表

请求URL：

- http://域名/finder/getMentionList

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| lastBuff | 是 | String | 翻页的key，首次传空，翻页传接口返回的lastBuff |
| myUserName | 是 | String | 自己的用户编码（获取个人主页接口返回的userName） |
| myRoleType | 是 | int | 自己的角色类型，根据角色关注（获取个人主页接口返回的roleType） |
| reqScene | 是 | int | 消息类型，3是点赞 4是评论 5是关注 |

请求参数示例

```
{
    "wId": "{{wId}}",
    "lastBuff": "",
    "myUserName":"v2_060000231003b20faec8cae18ec5d0cb07ea33b077ba915250774edbea38082ea6b24af229@finder",
    "myRoleType": 3,
    "reqScene":3
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "获取消息列表成功",
    "data": {
        "lastBuff": "CC0QAA==",
        "list": [
            {
                "flag": 0,
                "svrMentionId": 45,
                "headUrl": "https://wx.qlogo.cn/mmhead/ver_1/3JCic2WWGNg5Xic05huQEvDksIYMiaiaqXBpTQKUS1c9HFh8hwKWiadZiczuj0woaHYoHuyCNU2Nt8MSBJLx420RG57zkbxpEeu59iaNqadmxJqQ/132",
                "description": "我-要-带-他  #奥利奥 ",
                "followReason": {
                    "followReasonType": 1
                },
                "extInfo": {
                    "appName": "",
                    "entityId": ""
                },
                "likeInfo": {
                    "followMyFirstLike": 1,
                    "likeId": 14427663669542524928,
                    "likeType": 1
                },
                "refObjectNonceId": "16545206785312904238",
                "contact": {
                    "relationType": 1,
                    "contact": {
                        "nickname": "阿",
                        "headUrl": "https://wx.qlogo.cn/mmhead/ver_1/3JCic2WWGNg5Xic05huQEvDksIYMiaiaqXBpTw2QKUS9HFh8hwKWiadZiczuj0woaHYoHuyCNU2Nt8MSBJLx420RG57zkbxpEeu59iaNqadmxJqQ/132",
                        "username": "v5_020b0a166104010000000000f97523fa9f9a980000b1afa7d8728e3dd43ef4317a780e33c2996857e4fdf7e8b0f6772a3d0ed77295b3d890228fa85a9b3fee4fcea2e482220cc39f99b859576a7cdc4350fe20426405885897b149a5e97b8b4747be@stranger"
                    }
                },
                "nickname": "阿",
                "mentionType": 7,
                "thumbUrl": "http://wxapp.tc.qq.com/251/20304/stodownload?encfilekey=rjD5jyTuFrIpZ2ibE8T7YmwgiahniaXswqziawqWSSdH0BbkiawrwDXSEEAmbWcUr69CABn2N6heg1YkWbjJPS3C65iaciaD08HCdptD9VjASGtT4Lqzmn4zK9hYg&token=6xykWLEnztKIzBicPuvgFxrvplE8JAFDJ5CwrFMoQbeYhaqV28N5ITVvTdsIhnEAXTTAJHvVcbYtnmawnzsd4qZSejk2I0PPbMgT5ujNB5nvcs0X6yXTUWUC&idx=1&dotrans=0&hy=SH&m=&scene=2&uzid=2",
                "extflag": 0,
                "createtime": 1719911551,
                "refCommentId": 0,
                "orderCount": 0,
                "mediaType": 4,
                "mentionId": 68719476780,
                "finderIdentity": {},
                "refObjectId": 14426124740495808818,
                "refObjectType": 0,
                "authorContact": {
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
                    "signature": "国家一级运动员",
                    "headUrl": "https://wx.qlogo.cn/finderhead/ver_1/Vbwzoo1QIFPsR3GtNM4nC8jMMfbwsqQ0CSflEeFnmmzdj5RHOeoA1x9pYMKVo8NneKiaZOtibs6Z3X9opESubUe9oRp4Zv1aDC0Aztibo/0",
                    "authInfo": {
                        "authIconType": 1,
                        "authProfession": "体育博主",
                        "appName": "gh_4ee146ecaa@app",
                        "detailLink": "pages/index/index.html?showdetail=true&username=v2_060000231003b20fae4e28a1dc6d4ce04eb35b07734d2a64d661f5f4f8fb8178de6c4a63d@finder"
                    },
                    "extInfo": {
                        "country": "CN",
                        "province": "Jiangsu",
                        "city": "Nanjing",
                        "sex": 2
                    },
                    "coverImgUrl": "http://mmsns.qpic.cn/mmsns/vjAoL8Pl64W0P9frlndiaMGlza0RsNm2ibKbu094YJCmOY8FZRia84NLOriboF2A7sRd6RicOcsRicQ/0",
                    "extFlag": 2359308,
                    "originalFlag": 2,
                    "liveCoverImgUrl": "",
                    "nickname": "王",
                    "liveStatus": 2,
                    "username": "v2_060000231003b20faec8c4e28a1dc6d4ce04e5b07734d2a64d661f5f4f8fb8178de6c4a63d@finder",
                    "originalEntranceFlag": 1,
                    "status": 0
                },
                "mentionContent": "<_wc_custom_img_ color=\"FG_0\" src=\"finder://dynamic_icon/FinderObjectDynamicImageKey_FinderLikeIconPng\" />",
                "refContent": "",
                "username": "wxid_tdkou9quqz22"
            }
        ]
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