- 浏览

## 浏览

请求URL：

- http://域名/finderBrowse

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| objectId | 是 | bigint | 视频号作品id |
| objectNonceId | 是 | String | 视频号作品nonceId |
| sessionBuffer | 是 | String | 通过获取用户主页返回的sessionBuffer |
| myUserName | 是 | String | 自己的用户编码（获取个人主页接口返回的userName） |
| myRoleType | 是 | int | 自己的角色类型，根据角色关注（获取个人主页接口返回的roleType） |

请求参数示例

```
{
{
    "wId": "{{wId}}",
    "objectId": 14200825020179157073,
    "objectNonceId": "1614432821379421505_0_0_2_2_0",
    "sessionBuffer": "eyJzZXNzaW9uX2lkIjoic2lkXzEzNDUxMDA3MDNfMTY5NDQ5OTM1NzE4MDM0M18yMDI4Mjg4MDM0IiwiY3VyX2xpa2VfY291bnQiOjY2Mzc1NiwiY3VyX2NvbW1lbnRfY291bnQiOjU1MjYsInJlY2FsbF90eXBlcyI6W10sImRlbGl2ZXJ5X3NjZW5lIjoyLCJkZWxpdmVyeV90aW1lIjoxNjk0NDk5MzU3LCJzZXRfY29uZGl0aW9uX2ZsYWciOjksImZyaWVuZF9jb21tZW50X2luZm8iOnsibGFzdF9mcmllbmRfdXNlcm5hbWUiOiJ3eGlkX2k2cXNiYmplbmp1ajIyIiwibGFzdF9mcmllbmRfbGlrZV90aW1lIjoxNjk0NDk1ODI0fSwidG90YWxfZnJpZW5kX2xpa2VfY291bnQiOjEsInJlY2FsbF9pbmRleCI6W10sIm1lZGlhX3R5cGUiOjQsInZpZF9sZW4iOjYxLCJjcmVhdGVfdGltZSI6MTY5Mjg3MDI2MSwicmVjYWxsX2luZm8iOltdLCJzZWNyZXRlX2RhdGEiOiJCZ0FBTnBUcXRwUEZ6U3V0ZXZFakJlSDdzdXJjWUN1TmdsWlQrMXc0bnpDTlwvY1ZOb0lyeFFnbUhtTDNaa1ZIOThaZm9JRXJJR3ZOME81K0gyVzh2dk1YSkx0c0R0NFJrV2c9PSIsImlkYyI6MSwiZGV2aWNlX3R5cGVfaWQiOjEzLCJkZXZpY2VfcGxhdGZvcm0iOiJpUGFkMTMsMTkiLCJmZWVkX3BvcyI6MCwiY2xpZW50X3JlcG9ydF9idWZmIjoie1wiaWZfc3BsaXRfc2NyZWVuX2lwYWRcIjowLFwiZW50ZXJTb3VyY2VJbmZvXCI6XCJ7XFxcImZpbmRlcnVzZXJuYW1lXFxcIjpcXFwiXFxcIixcXFwiZmVlZGlkXFxcIjpcXFwiXFxcIn1cIixcImV4dHJhaW5mb1wiOlwie1xcbiBcXFwicmVnY291bnRyeVxcXCIgOiBcXFwiQ05cXFwiXFxufVwiLFwic2Vzc2lvbklkXCI6XCJTcGxpdFZpZXdFbXB0eVZpZXdDb250cm9sbGVyXzE2OTQ0OTkyNzIxNDQjJDBfMTY5NDQ5OTI1OTUwOCNcIixcImp1bXBJZFwiOntcInRyYWNlaWRcIjpcIlwiLFwic291cmNlaWRcIjpcIlwifX0iLCJvYmplY3RfaWQiOjE0MjAwODI1MDIwMTc5MTU3MDczLCJmaW5kZXJfdWluIjoxMzEwNDgwNDQ5OTAxODE3OCwiZ2VvaGFzaCI6MzM3NzY5OTcyMDUyNzg3MiwicnFzdG0iOjE2OTQ0OTkzNTY3NDcsInJzc3RtIjoxNjk0NDk5MzU3MjEwLCJycWN0bSI6MTY5NDQ5OTI4MDQwMiwiZW50cmFuY2Vfc2NlbmUiOjIsImNhcmRfdHlwZSI6MywiZXhwdF9mbGFnIjoyMTY3OTA5MSwidXNlcl9tb2RlbF9mbGFnIjo4LCJjdHhfaWQiOiIyLTMtMzItMTI0N2E0YjVhOTQ4YzI4Yjg0NWZiM2Y0N2EyNTE4M2ExNjk0NDk5Mjc3MjcwIiwib2JqX2ZsYWciOjEzNDI1MDQ5NiwiZXJpbCI6W10sInBna2V5cyI6W10sIm9ial9leHRfZmxhZyI6OTg1MTJ9",
    "myUserName": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx@finder",
    "myRoleType": "3"
} 
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "视频号浏览成功",
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