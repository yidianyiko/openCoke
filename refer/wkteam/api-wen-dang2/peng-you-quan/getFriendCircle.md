- 获取某个好友的朋友圈

## 获取某个好友的朋友圈

简要描述：

- 获取某个好友的朋友圈

[!DANGER]本接口返回xml的图片与视频链接无法直接查看，需要调用获取某条朋友圈详细内容接口查看

请求URL：

- http://域名地址/getFriendCircle

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| wcId | 是 | String | 微信id |
| firstPageMd5 | 是 | String | 首页传:""，第2页及以后传返回的firstPageMd5 （PS：firstPageMd5为null情况下，则用上次不为null的值） |
| maxId | 是 | long | 首页传：0（PS：第2页及以后用返回数据最后一个条目的id） |

请求参数示例

```
{
    "wId": "0000016e-68f9-99d5-0002-3a1cd9eaaa17",
    "wcId": "xxxxxx",
    "firstPageMd5": "",
    "maxId":0
}

```

成功返回示例

```
{
    "message": "成功",
    "code": "1000",
    "data": {
        "sns": [
             {
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

                    }
                ],
                "commentCount": xxxxxx,
                "snsComments": []
            },
            ......
        ],
        "firstPageMd5": "xxxxxx"
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
| firstPageMd5 | String |