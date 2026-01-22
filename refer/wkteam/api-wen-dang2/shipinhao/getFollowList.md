- 获取关注列表

## 获取关注列表

请求URL：

- http://域名/finder/getFollowList

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| lastBuff | 否 | String | 首次传空，后续传接口返回的lastBuffer |
| myUserName | 是 | String | 自己的用户编码（获取个人主页接口返回的userName） |
| myRoleType | 是 | int | 自己的角色类型，根据角色关注（获取个人主页接口返回的roleType） |

请求参数示例

```
{
    "wId": "2c7a5bf6-e23d-x-8f03-b90e844b539f",
    "lastBuff": "",
    "myUserName":"v2_060000231003b20faec8cae18cb07ea33b077ba915250774edbea38082ea6b24af229@finder",
    "myRoleType": 3
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
                    "anchorStatusFlag": 133248,
                    "lotterySetting": {
                        "attendType": 4,
                        "settingFlag": 0
                    }
                },
                "signature": "。。。",
                "headUrl": "https://wx.qlogo.cn/finderhead/ver_1/vfEnTh99QtHJXzs4hA4iar7vIRQGqZ4esmpUKlbGF2enPDVeUAUkPqonibqiaNlgaO5UZGX5FZ2rQuZec6Lrq74KPcqL9JPmnsCBrJlOGFJs/0",
                "authInfo": {},
                "extInfo": {
                    "country": "CN",
                    "province": "",
                    "city": "",
                    "sex": 2
                },
                "coverImgUrl": "",
                "extFlag": 262156,
                "followTime": 1718847606,
                "liveCoverImgUrl": "http://wxapp.tc.qq.com/251/20350/stodownload?m=be88b1cb981aa72b3328ccbd22a58e0b&filekey=30340201010420301e020200fb0403480410be88b1cb981aa72b3328ccbd22a58e0b02022814040d00000004627466730000000132&hy=SH&storeid=5649443df0009b8a38399cc84000000fb00004f7e534815c008e0b08dc805c&dotrans=0&bizid=1023",
                "nickname": "朝vvvv",
                "followFlag": 1,
                "liveStatus": 2,
                "username": "v2_060000231003b20faec8c6e18f10c7d6c903ec776955d3d97c6b329d6aa58693bcdb7ad1@finder",
                "status": 0
            }
        ],
        "lastBuffer": "CL+fAxu8+qqBg==",
        "followCount": 1,
        "continueFlag": 1
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