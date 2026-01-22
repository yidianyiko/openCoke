- 转发朋友圈

## 转发朋友圈

[!DANGER]

- 微信需在线三天后使用本接口，否则微信团队会提示不可使用副设备发送
- 本接口可以转发除了图片任意朋友圈内容，图片朋友圈建议调用发布接口

简要描述：

- 转发朋友圈，直接xml数据。(对谁不可见)

请求URL：

- http://域名地址/forwardSns

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| content | 是 | String | 收到的xml |
| blackList | 否 | String | 对谁不可见（传微信id,多个用,分隔） |
| withUserList | 否 | String | 对谁可见 （传微信id,多个用,分隔） |

请求参数示例

```
{
     "wId": "xxxxxxx",
     "content": "xxxxxxx"
}

```

成功返回示例

```
{
    "message": "成功",
    "code": "1000",
    "data": {
        "id": "xxxxxxx",
        "userName": "xxxxxxx",
        "nickName": "xxxxxxx",
        "createTime": xxxxxxx,
        "objectDesc": {
            "xml": "xxxxxxx",
            "len": xxxxxxx
        },
        "likeCount": xxxxxxx,
        "snsLikes": [],
        "commentCount": xxxxxxx,
        "snsComments": []
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
| code | string | 1000成功，1001失败 |
| msg | String | 反馈信息 |
| id | String | 朋友圈ID |
| userName | String | 微信id |
| createTime | String | 时间 |
| objectDesc | JSONObject | 朋友圈内容 |
| xml | String | 朋友圈xml |
| len | int | xml 长度 |
| commentId | int | 评论标识 |
| replyCommentId | int | 回复评论标识 |
| deleteFlag | int | 删除标识 |
| isNotRichText | int | 是否试富文本 |
| content | String | 评论内容 |
| commentId | int | 评论ID |
| snsLikes | JSONArray | 点赞用户列表 |
| userName | String | 微信id |
| nickName | String | 昵称 |
| type | int | 点赞类型 |
| createTime | int | 点赞时间 |