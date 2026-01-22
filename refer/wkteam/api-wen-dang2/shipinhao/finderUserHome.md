- 获取用户主页

## 获取用户主页

请求URL：

- http://域名/finderUserHome

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| userName | 是 | String | 视频号用户的编码（搜索接口返回的userName） |
| pageCode | 否 | String | 分页参数，首次传空，获取下一页时传响应中返回的pageCode |

请求参数示例

```
{
    "wId": "2c7a5bf6-e23d-x-8f03-b90e844b539f",
    "userName": "v2_060000231003b20faec8c6e48f11c7d2c901e531b077a130b51b4788d2af47a9375e2e776c46@finder",
    "pageCode": ""
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "处理成功",
    "data": {
        "videoList": [{
            "id": 13897021715463014565,
            "nickName": "摩托欧耶",
            "userName": "v2_060000231003b20faec8c6e48f11c7d2c901e531b077a130b51b4788d2af47a9375e2e776c46@finder",
            "createTime": 1656654085,
            "forwardCount": 96,
            "likeCount": 114,
            "commentCount": 64,
            "friendLikeCount": 0,
            "objectNonceId": "10833141393859919979_0_0_2_1",
            "sessionBuffer": "eyJzZXNzaW9uX2lkIjoic2lkXzIyMDc4OTQ2NjBfMTY1NzI5MzcwMTc0MDc0OF8yOTY2MTIxNjgiLCJjdXJfbGlrZV9jb3VudCI6MTE0LCJjdXJfY29tbWVudF9jb3VudCI6NjQsInJlY2FsbF90eXBlcyI6W10sImRlbGl2ZXJ5X3NjZW5lIjoyLCJkZWxpdmVyeV90aW1lIjoxNjU3MjkzNzAxLCJzZXRfY29uZGl0aW9uX2ZsYWciOjksInJlY2FsbF9pbmRleCI6W10sIm1lZGlhX3R5cGUiOjQsInZpZF9sZW4iOjEwNTIsImNyZWF0ZV90aW1lIjoxNjU2NjU0MDg1LCJyZWNhbGxfaW5mbyI6W10sInNlY3JldGVfZGF0YSI6IkJnQUFMXC9DOU5ma2hQQTVvRm05aXhtMFU2SHZVQm9NanVcLzNtRWZrNnplSzVjcUJmbERIWlh5M2gwMHBWMlpFZ2lnKzhqSFh6czhJRTFSSU1cL1IwZVVnZEwiLCJkZXZpY2VfdHlwZV9pZCI6MTMsImRldmljZV9wbGF0Zm9ybSI6ImlQYWQxMSwzIiwidmlkZW9faWQiOjEzODk3MDIxNzEzNDEyMjYyMDIwLCJmZWVkX3BvcyI6MCwiY2xpZW50X3JlcG9ydF9idWZmIjoie1wiaWZfc3BsaXRfc2NyZWVuX2lwYWRcIjowLFwiZW50ZXJTb3VyY2VJbmZvXCI6XCJ7XFxcImZpbmRlcnVzZXJuYW1lXFxcIjpcXFwiXFxcIixcXFwiZmVlZGlkXFxcIjpcXFwiXFxcIn1cIixcImV4dHJhaW5mb1wiOlwiXCIsXCJzZXNzaW9uSWRcIjpcIjE0M18xNjU3MjkzNjQxMjgxIyQyXzE2NTcyOTM2MzE1OTcjXCIsXCJqdW1wSWRcIjp7XCJ0cmFjZWlkXCI6XCJcIixcInNvdXJjZWlkXCI6XCJcIn19Iiwib2JqZWN0X2lkIjoxMzg5NzAyMTcxNTQ2MzAxNDU2NSwiZmluZGVyX3VpbiI6MTMxMDQ4MDQ3Njg0Nzc1OTUsImNpdHkiOiLljJfkuqzluIIiLCJnZW9oYXNoIjo0MDY5MTQzMDYxMzA2MTQ1LCJycXN0bSI6MTY1NzI5MzcwMTIxOCwicnNzdG0iOjE2NTcyOTM3MDE4ODgsInJxY3RtIjozNzMxMjkxNjA5LCJlbnRyYW5jZV9zY2VuZSI6MSwiY2FyZF90eXBlIjoxLCJleHB0X2ZsYWciOjU3NTk4NywidXNlcl9tb2RlbF9mbGFnIjo4LCJjdHhfaWQiOiIxLTEtMjAtMDI2YjI5YzRhZjBkOGZkODY3N2ZiOWQ0NWE1M2E0MzQxNjU3MjkzNzAxIn0=",
            "favCount": 50,
            "urlValidTime": 172800,
            "finderUser": {
                "userName": "v2_060000231003b20faec8c6e48f11c7d2c901e531b077a130b51b4788d2af47a9375e2e776c46@finder",
                "nickName": "摩托欧耶",
                "headUrl": "http://wx.qlogo.cn/finderhead/ver_1/x4IicA6aP1g8XAmf3UZ7yOm5PxPXVup6IyH7S9PbMa12wo2bCtNmjl17uNMryGQEkTFOqibruXu8OMCblictX3zNfvfBOGZxmbPsOttnJdbjSA/0",
                "signature": "喜欢摩托车就会关注",
                "authInfo": {
                    "authIconType": 2,
                    "authProfession": "北京自由摩力科技有限公司",
                    "detailLink": "pages/index/index.html?showdetail=true&username=v2_060000231003b20faec8c6e48f11c7d2c901e531b077a130b51b4788d2af47a9375e2e776c46@finder",
                    "appName": "gh_4ee148a6ecaa@app"
                },
                "extInfo": null,
                "userMode": 2,
                "bindInfo": "CAEShQIKggIKD2doXzFkZDdjNzJhMzM5YRIM5pGp5omY5qyn6IC2GldodHRwOi8vd3gucWxvZ28uY24vbW1oZWFkL1EzYXVIZ3p3ek03VzZVZmx3aWFyVnBOWlZ4RHVxREFkVnNRWjBXb2RpYUhIbDRPZHNLaWJlTHRsZy8xMzIyhwEIAhKCAWh0dHBzOi8vZGxkaXIxdjYucXEuY29tL3dlaXhpbi9jaGVja3Jlc3VwZGF0ZS9pY29uc19maWxsZWRfY2hhbm5lbHNfYXV0aGVudGljYXRpb25fZW50ZXJwcmlzZV9hMjY1ODAzMjM2ODI0NTYzOWU2NjZmYjExNTMzYTYwMC5wbmc="
            },
            "videoDetails": {
                "desc": "过个减速带就断了，意塔杰特前摇臂货不对版#摩托车\n",
                "mediaType": 4,
                "mediaList": [{
                    "url": "http://wxapp.tc.qq.com/251/20302/stodownload?encfilekey=Cvvj5Ix3eewK0tHtibORqcsqchXNh0Gf3sJcaYqC2rQDJNFRLRa1na4ibz2icCIgtsska1JH3v9O3MKLwxP7j3ZKdvVicE8I8YwE9aAExw8ZuZcrDOBgxIqxznMzqmP6Ricmz&adaptivelytrans=943&bizid=1023&dotrans=3071&hy=SH&idx=1&m=",
                    "thumbUrl": "http://wxapp.tc.qq.com/251/20304/stodownload?encfilekey=rjD5jyTuFrIpZ2ibE8T7YmwgiahniaXswqzRV15Tk2pGjBicLwDUFt0fkaj6H1VDJyCUdyZ6OIw9ribMRicdV3diblTWu2FjnF6PkkjNa3qgJ4rYDkYPGTS7XAIQg&adaptivelytrans=0&bizid=1023&dotrans=0&hy=SH&idx=1&m=&scene=0",
                    "mediaType": 4,
                    "videoPlayLen": 1052,
                    "width": 1920,
                    "height": 1080,
                    "md5": "9df282dfc0f355f7c5c8260970602a3d",
                    "fileSize": 1077630854
                }],
                "location": {
                    "longitude": "116.14294",
                    "latitude": "39.74788",
                    "city": "北京市"
                },
                "finderTopicInfo": "<finder><version>1</version><valuecount>3</valuecount><style><at></at></style><value0><![CDATA[过个减速带就断了，意塔杰特前摇臂货不对版]]></value0><value1><topic><![CDATA[#摩托车#]]></topic></value1><value2><![CDATA[\n]]></value2></finder>",
                "commentList": null
            },
            "commentList": [{
                "userName": "v5_020b0a166104010000000000489a3a1d7ba12d000000b1afa7d8728e3dd43ef4317a780e33c2996857e4fdf7e8b0f6772a3d0ed03edf984fe1e17f31c39207f75c1d6ff53b4f2e492e1a3c03a64e41998c0945b68ddc9a714512c95d45b1be796545ec@stranger",
                "nickName": "坚持",
                "content": "听着着急/::D/::D",
                "commentId": 598083965,
                "replyCommentId": 0,
                "headUrl": "https://wx.qlogo.cn/mmhead/ver_1/8PbBDnrv02mswaZHRsIONfX1umT6LfD4klfBeW6uQLgfsEDW0gEFAfaezLu9lFzbDu22JrrzLjbg9AhD1YG2qPibia4bUbibSxQRZGmKkL7ZtQ/132",
                "createTime": 1657076433,
                "likeCount": null,
                "ipRegion": null,
                "replyContent": null,
                "replyUserName": "",
                "finderAuthorVo": null
            }]
        }, {
            "id": 13891898139715504258,
            "nickName": "摩托欧耶",
            "userName": "v2_060000231003b20faec8c6e48f11c7d2c901e531b077a130b51b4788d2af47a9375e2e776c46@finder",
            "createTime": 1656043307,
            "forwardCount": 81,
            "likeCount": 63,
            "commentCount": 34,
            "friendLikeCount": 0,
            "objectNonceId": "11991040772444765212_0_0_2_1",
            "sessionBuffer": "eyJzZXNzaW9uX2lkIjoic2lkXzIyMDc4OTQ2NjBfMTY1NzI5MzcwMTc0MDc0OF8yOTY2MTIxNjgiLCJjdXJfbGlrZV9jb3VudCI6NjMsImN1cl9jb21tZW50X2NvdW50IjozNCwicmVjYWxsX3R5cGVzIjpbXSwiZGVsaXZlcnlfc2NlbmUiOjIsImRlbGl2ZXJ5X3RpbWUiOjE2NTcyOTM3MDEsInNldF9jb25kaXRpb25fZmxhZyI6OSwicmVjYWxsX2luZGV4IjpbXSwibWVkaWFfdHlwZSI6NCwidmlkX2xlbiI6MzExLCJjcmVhdGVfdGltZSI6MTY1NjA0MzMwNywicmVjYWxsX2luZm8iOltdLCJzZWNyZXRlX2RhdGEiOiJCZ0FBdjJ3ckFGeDdTYjNTNzh2OUFHOHZnMG1ueHlcLzVtd0NIT2lmbk04a0h6MGNoMjNiVnl6S1d2ZjdJeW9hcjlBalZjODdZWVFMQ1NYcTE5RTY1Mm9PciIsImRldmljZV90eXBlX2lkIjoxMywiZGV2aWNlX3BsYXRmb3JtIjoiaVBhZDExLDMiLCJ2aWRlb19pZCI6MTM4OTE4OTgxMzY3MzIyNDAwMzQsImZlZWRfcG9zIjoxLCJjbGllbnRfcmVwb3J0X2J1ZmYiOiJ7XCJpZl9zcGxpdF9zY3JlZW5faXBhZFwiOjAsXCJlbnRlclNvdXJjZUluZm9cIjpcIntcXFwiZmluZGVydXNlcm5hbWVcXFwiOlxcXCJcXFwiLFxcXCJmZWVkaWRcXFwiOlxcXCJcXFwifVwiLFwiZXh0cmFpbmZvXCI6XCJcIixcInNlc3Npb25JZFwiOlwiMTQzXzE2NTcyOTM2NDEyODEjJDJfMTY1NzI5MzYzMTU5NyNcIixcImp1bXBJZFwiOntcInRyYWNlaWRcIjpcIlwiLFwic291cmNlaWRcIjpcIlwifX0iLCJvYmplY3RfaWQiOjEzODkxODk4MTM5NzE1NTA0MjU4LCJmaW5kZXJfdWluIjoxMzEwNDgwNDc2ODQ3NzU5NSwiY2l0eSI6IuWMl+S6rOW4giIsImdlb2hhc2giOjQwNjk4ODUzNzIxNTk5NzQsInJxc3RtIjoxNjU3MjkzNzAxMjE4LCJyc3N0bSI6MTY1NzI5MzcwMTg4OSwicnFjdG0iOjM3MzEyOTE2MDksImVudHJhbmNlX3NjZW5lIjoxLCJjYXJkX3R5cGUiOjEsImV4cHRfZmxhZyI6NTc1OTg3LCJ1c2VyX21vZGVsX2ZsYWciOjgsImN0eF9pZCI6IjEtMS0yMC0wMjZiMjljNGFmMGQ4ZmQ4Njc3ZmI5ZDQ1YTUzYTQzNDE2NTcyOTM3MDEifQ==",
            "favCount": 27,
            "urlValidTime": 172800,
            "finderUser": {
                "userName": "v2_060000231003b20faec8c6e48f11c7d2c901e531b077a130b51b4788d2af47a9375e2e776c46@finder",
                "nickName": "摩托欧耶",
                "headUrl": "http://wx.qlogo.cn/finderhead/ver_1/x4IicA6aP1g8XAmf3UZ7yOm5PxPXVup6IyH7S9PbMa12wo2bCtNmjl17uNMryGQEkTFOqibruXu8OMCblictX3zNfvfBOGZxmbPsOttnJdbjSA/0",
                "signature": "喜欢摩托车就会关注",
                "authInfo": {
                    "authIconType": 2,
                    "authProfession": "北京自由摩力科技有限公司",
                    "detailLink": "pages/index/index.html?showdetail=true&username=v2_060000231003b20faec8c6e48f11c7d2c901e531b077a130b51b4788d2af47a9375e2e776c46@finder",
                    "appName": "gh_4ee148a6ecaa@app"
                },
                "extInfo": null,
                "userMode": 2,
                "bindInfo": "CAEShQIKggIKD2doXzFkZDdjNzJhMzM5YRIM5pGp5omY5qyn6IC2GldodHRwOi8vd3gucWxvZ28uY24vbW1oZWFkL1EzYXVIZ3p3ek03VzZVZmx3aWFyVnBOWlZ4RHVxREFkVnNRWjBXb2RpYUhIbDRPZHNLaWJlTHRsZy8xMzIyhwEIAhKCAWh0dHBzOi8vZGxkaXIxdjYucXEuY29tL3dlaXhpbi9jaGVja3Jlc3VwZGF0ZS9pY29uc19maWxsZWRfY2hhbm5lbHNfYXV0aGVudGljYXRpb25fZW50ZXJwcmlzZV9hMjY1ODAzMjM2ODI0NTYzOWU2NjZmYjExNTMzYTYwMC5wbmc="
            },
            "videoDetails": {
                "desc": "鑫源1200发动机点火，需要哈雷感应钥匙帮忙吗？#鑫源 #公升级#发动机 #哈雷 #摩托车 #机车\n",
                "mediaType": 4,
                "mediaList": [{
                    "url": "http://wxapp.tc.qq.com/251/20302/stodownload?encfilekey=Cvvj5Ix3eewK0tHtibORqcsqchXNh0Gf3sJcaYqC2rQCPemqTON4YcuzCR6l0D1kDH6lhq9qKgHaNiaKMpMLStug3Jv3ibfgSoDTGSjAhM78nvFPSrWegahGrHKYsPaMXSL&adaptivelytrans=943&bizid=1023&dotrans=2991&hy=SH&idx=1&m=",
                    "thumbUrl": "http://wxapp.tc.qq.com/251/20304/stodownload?encfilekey=rjD5jyTuFrIpZ2ibE8T7YmwgiahniaXswqzJfdYzXO9sI2oEcLPBNkcggKbiaCYiaEOgTsBRVY67DFynibOY067iaA9boRsvY5ODDCSCaTHYpwIyV2hA9KBArwC1w&adaptivelytrans=0&bizid=1023&dotrans=0&hy=SH&idx=1&m=&scene=0",
                    "mediaType": 4,
                    "videoPlayLen": 311,
                    "width": 1920,
                    "height": 1080,
                    "md5": "de8278ac9bd0aa099eca26a371e8040f",
                    "fileSize": 341585171
                }],
                "location": {
                    "longitude": "116.40717",
                    "latitude": "39.90469",
                    "city": "北京市"
                },
                "finderTopicInfo": "<finder><version>1</version><valuecount>12</valuecount><style><at></at></style><value0><![CDATA[鑫源1200发动机点火，需要哈雷感应钥匙帮忙吗？]]></value0><value1><topic><![CDATA[#鑫源#]]></topic></value1><value2><![CDATA[ ]]></value2><value3><topic><![CDATA[#公升级#]]></topic></value3><value4><topic><![CDATA[#发动机#]]></topic></value4><value5><![CDATA[ ]]></value5><value6><topic><![CDATA[#哈雷#]]></topic></value6><value7><![CDATA[ ]]></value7><value8><topic><![CDATA[#摩托车#]]></topic></value8><value9><![CDATA[ ]]></value9><value10><topic><![CDATA[#机车#]]></topic></value10><value11><![CDATA[\n]]></value11></finder>",
                "commentList": null
            },
            "commentList": [{
                "userName": "v5_020b0a166104010000000000b9a2096005754d000000b1afa7d8728e3dd43ef4317a780e33c2996857e4fdf7e8b0f6772a3d0e5ba432b1511eb92abc4c3abdd821764cf336148f466448764bd6f4e352e4399e@stranger",
                "nickName": "陈无非",
                "content": "换个人说吧  话都说不利索",
                "commentId": 2002061707,
                "replyCommentId": 0,
                "headUrl": "https://wx.qlogo.cn/mmhead/ver_1/VMoBWQ7ibpwP809n9ynXmnInC78ZrOoQn3mz7creYcDGRsoDMGAjSuv4JsLNmAzj9BSWCf93KQ53v6FubT6x7MA/132",
                "createTime": 1656357877,
                "likeCount": null,
                "ipRegion": null,
                "replyContent": null,
                "replyUserName": "",
                "finderAuthorVo": null
            }]
        }, ],
        "userInfo": {
            "userName": "v2_060000231003b20faec8c6e48f11c7d2c901e531b077a130b51b4788d2af47a9375e2e776c46@finder",
            "nickName": "摩托欧耶",
            "headUrl": "http://wx.qlogo.cn/finderhead/ver_1/x4IicA6aP1g8XAmf3UZ7yOm5PxPXVup6IyH7S9PbMa12wo2bCtNmjl17uNMryGQEkTFOqibruXu8OMCblictX3zNfvfBOGZxmbPsOttnJdbjSA/0",
            "signature": "喜欢摩托车就会关注",
            "authInfo": {
                "authIconType": 2,
                "authProfession": "北京自由摩力科技有限公司",
                "detailLink": "pages/index/index.html?showdetail=true&username=v2_060000231003b20faec8c6e48f11c7d2c901e531b077a130b51b4788d2af47a9375e2e776c46@finder",
                "appName": "gh_4ee148a6ecaa@app"
            },
            "extInfo": null,
            "userMode": 2,
            "bindInfo": "CAEShQIKggIKD2doXzFkZDdjNzJhMzM5YRIM5pGp5omY5qyn6IC2GldodHRwOi8vd3gucWxvZ28uY24vbW1oZWFkL1EzYXVIZ3p3ek03VzZVZmx3aWFyVnBOWlZ4RHVxREFkVnNRWjBXb2RpYUhIbDRPZHNLaWJlTHRsZy8xMzIyhwEIAhKCAWh0dHBzOi8vZGxkaXIxdjYucXEuY29tL3dlaXhpbi9jaGVja3Jlc3VwZGF0ZS9pY29uc19maWxsZWRfY2hhbm5lbHNfYXV0aGVudGljYXRpb25fZW50ZXJwcmlzZV9hMjY1ODAzMjM2ODI0NTYzOWU2NjZmYjExNTMzYTYwMC5wbmc="
        },
        "pageCode": "CJuRpLG5y7fbvwEQARgAIKWRwJDu84juwAEggpGcjZf4++TAASCHkajO5PGS4cABIKGR8PXI9o7bwAEgpJH0mN6HjdvAASCOkeiM3qK42cABIImRqJfC6Y+PwAEgiZHwwLjax4fAASCRkeDM7/XmhcABIJ2R2NvXnfX4vwEgopHYkYvfnPS/ASCfkYCdpcyn8L8BIJGRjJLpmf3vvwEgkpGE4+iIh+i/ASCbkaSxucu3278B",
        "friendFollowCount": 0
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