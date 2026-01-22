- 获取某条朋友圈详细内容

## 获取某条朋友圈详细内容

简要描述：

- 获取某条朋友圈详细内容

请求URL：

- http://域名地址/getSnsObject

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| wcId | 是 | String | 好友微信id |
| id | 是 | String | 朋友圈标识 |

请求参数示例

```
{
     "wId": "b7ad08a6-77c2-4ad6-894a-29993b84c0e4",
     "wcId": "wxid_6tn88z16x6ou12",
     "id": 13351161735026061409
}

```

成功返回示例

```
{
    "message": "成功",
    "code": "1000",
    "data": {
        "id": "xxxxxx",
        "userName": "xxxxxx",
        "nickName": "xxxxxx",
        "createTime": xxxxxx,
        "objectDesc": {
            "xml": "xxxxxx",
            "len": xxxxxx
        },
        "likeCount": xxxxxx,
        "snsLikes": [
            {
                "userName": "xxxxxx",
                "nickName": "xxxxxx",
                "type": xxxxxx,
                "createTime": xxxxxx
            },
            ......
        ],
        "commentCount": xxxxxx,
        "snsComments": [
            {
                "userName": "xxxxxx",
                "nickName": xxxxxx,
                "type": xxxxxx,
                "createTime": xxxxxx,
                "commentId": xxxxxx,
                "replyCommentId": xxxxxx,
                "deleteFlag": xxxxxx,
                "isNotRichText": xxxxxx,
                "content": "xxxxxx"
            },
            ......
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
| code | string | 1000成功，1001失败 |
| msg | String | 反馈信息 |
| data |
| id | String | 朋友圈ID |
| userName | String | 微信id |
| nickName | String | 昵称 |
| createTime | String | 时间 |
| objectDesc | JSONObject | 朋友圈内容 |
| xml | String | 朋友圈xml |
| len | int | xml 长度 |
| snsComments | JSONArray | 评论用户列表 |
| userName | String | 微信id |
| nickName | String | 昵称 |
| type | int | 评论类型 |
| createTime | int | 评论时间 |
| commentId | int | 评论标识 | replyCommentId |
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