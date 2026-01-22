- 修改视频号资料

## 修改视频号资料

请求URL：

- http://域名/modFinderProfile

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| meUserName | 是 | String | 自己的用户编码（获取个人主页接口返回的userName） |
| meRoleType | 是 | int | 自己的角色类型，根据角色关注（获取个人主页接口返回的roleType） |
| nickName | 是 | String | 视频号昵称 |
| signature | 是 | String | 视频号简介 |
| headImgUrl | 是 | String | 视频号头像链接 |
| country | 是 | String | 国家 |
| province | 是 | String | 省份 |
| city | 是 | String | 城市 |
| sex | 是 | int | 性别 |

请求参数示例

```
{
    "wId": "{{wId}}",
    "meUserName": "v2_060000231003b20faec8c6e18f10c7d6c903ec3db0776955d3d97c6b329d6aa58693bcdb7ad1@finder",
    "meRoleType": 3,
    "nickName": "",
    "signature": "",
    "headImgUrl": "",
    "country": "",
    "province": "",
    "city": "",
    "sex": 2
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "视频号小红心id失败",
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