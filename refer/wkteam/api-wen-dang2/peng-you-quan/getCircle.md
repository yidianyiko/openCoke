- 获取朋友圈

## 获取朋友圈

简要描述：

- 获取朋友圈

请求URL：

- http://域名地址/getCircle

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| firstPageMd5 | 是 | String | 首次传""，第2页及以后传返回的firstPageMd5（PS：firstPageMd5为null情况下，则用上次不为null的值） |
| maxId | 是 | long | 首次传0（PS：第2页及以后用返回数据最后一个条目的id） |

请求参数示例

```
{
     "wId": "b7ad08a6-77c2-4ad6-894a-29993b84c0e4",
     "firstPageMd5": "",
     "maxId" : 0
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
                "id": "13351211557386072142",
                "userName": "wxid_6tn88z16x6ou12",
                "nickName": "远见",
                "createTime": 1591588444,
                "likeFlag": 0,
                "likeCount": 0,
                "snsLikes": [],
                "commentCount": 0,
                "snsComments": []
            },
            .......
        ],
        "firstPageMd5": "087ed4f0b41e46e3"
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