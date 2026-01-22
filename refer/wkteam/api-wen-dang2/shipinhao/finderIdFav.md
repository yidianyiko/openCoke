- 点赞

## 点赞

请求URL：

- http://域名/finderIdFav

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| id | 是 | bigint | 视频号作品id |
| nonceId | 是 | String | 视频号作品nonceId |
| type | 是 | int | 操作类型1:点赞2:取消点赞 |
| sessionBuffer | 是 | String | 通过获取用户主页返回的sessionBuffer |
| toUserName | 是 | String | 作者的username |
| meUserName | 是 | String | 自己的用户编码（获取个人主页接口返回的userName） |
| meRoleType | 是 | int | 自己的角色类型，根据角色关注（获取个人主页接口返回的roleType） |

请求参数示例

```
{
  {
    "wId": "{{wId}}",
    "id": 14200825020179157073,
    "nonceId": "",
    "type": 1,
    "sessionBuffer": "eyJzZXNzaW9uX2lkIjoic2lkXzEzNDUxMDA3MDNfMTY5NDQ5MTA1MDk3NDcxMl8xMDkyODAzNzIwIiwiY3VyX2xpa2VfY291bnQiOjY2Mzc1MywiY3VyX2NvbW1lbnRfY291bnQiOjU1MjMsInJlY2FsbF90eXBlcyI6W10sImRlbGl2ZXJ5X3NjZW5lIjoyLCJkZWxpdmVyeV90aW1lIjoxNjk0NDkxMDUxLCJzZXRfY29uZGl0aW9uX2ZsYWciOjksInJlY2FsbF9pbmRleCI6W10sIm1lZGlhX3R5cGUiOjQsInZpZF9sZW4iOjYxLCJjcmVhdGVfdGltZSI6MTY5Mjg3MDI2MSwicmVjYWxsX2luZm8iOltdLCJzZWNyZXRlX2RhdGEiOiJCZ0FBVlwvMUhmdkVDM2s0QkdhMVJ1SXlYdGZQYVdYTzBGVVg4UHdnWHpHTVZrRnBBOHRBclJ0Q0MzVEFEZXVEUW1aOThRMUhiUVk1TitGWHFkRmYxQ1dwMXZPVThsMkhNK1E9PSIsImlkYyI6MSwiZGV2aWNlX3R5cGVfaWQiOjEzLCJkZXZpY2VfcGxhdGZvcm0iOiJpUGFkMTMsMTkiLCJmZWVkX3BvcyI6MCwiY2xpZW50X3JlcG9ydF9idWZmIjoie1wiaWZfc3BsaXRfc2NyZWVuX2lwYWRcIjowLFwiZW50ZXJTb3VyY2VJbmZvXCI6XCJ7XFxcImZpbmRlcnVzZXJuYW1lXFxcIjpcXFwiXFxcIixcXFwiZmVlZGlkXFxcIjpcXFwiXFxcIn1cIixcImV4dHJhaW5mb1wiOlwie1xcbiBcXFwicmVnY291bnRyeVxcXCIgOiBcXFwiQ05cXFwiXFxufVwiLFwic2Vzc2lvbklkXCI6XCJTcGxpdFZpZXdFbXB0eVZpZXdDb250cm9sbGVyXzE2OTQ0OTA5NjYxNTEjJDBfMTY5NDQ5MDk1MzUxNSNcIixcImp1bXBJZFwiOntcInRyYWNlaWRcIjpcIlwiLFwic291cmNlaWRcIjpcIlwifX0iLCJvYmplY3RfaWQiOjE0MjAwODI1MDIwMTc5MTU3MDczLCJmaW5kZXJfdWluIjoxMzEwNDgwNDQ5OTAxODE3OCwiZ2VvaGFzaCI6MzM3NzY5OTcyMDUyNzg3MiwicnFzdG0iOjE2OTQ0OTEwNTA1MzMsInJzc3RtIjoxNjk0NDkxMDUxMDEwLCJycWN0bSI6MTY5NDQ5MDk3NDQwOSwiZW50cmFuY2Vfc2NlbmUiOjIsImNhcmRfdHlwZSI6MywiZXhwdF9mbGFnIjoyMTY3OTA5MSwidXNlcl9tb2RlbF9mbGFnIjo4LCJjdHhfaWQiOiIyLTMtMzItMTI0N2E0YjVhOTQ4YzI4Yjg0NWZiM2Y0N2EyNTE4M2ExNjk0NDkwOTcxMjc3Iiwib2JqX2ZsYWciOjEzNDI1MDQ5NiwiZXJpbCI6W10sInBna2V5cyI6W10sIm9ial9leHRfZmxhZyI6OTg1MTJ9=",
    "toUserName": "v2_060000231003b20faec8c6e78e11c3d0cf01e83cb077761114601a6de6df2f17ee579c1@finder",
    "meUserName": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx@finder",
    "meRoleType": "3"
}
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