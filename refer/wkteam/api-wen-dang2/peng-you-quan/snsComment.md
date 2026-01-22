- 朋友圈评论

## 朋友圈评论

简要描述：

- 朋友圈评论

请求URL：

- http://域名地址/snsComment

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| id | 是 | String | 朋友圈标识 |
| replyCommentId | 是 | int | 评论标识（回复评论） |
| content | 是 | String | 内容 |

请求参数示例

```
{
    "wId": "0000016e-abcd-0ea8-0002-d8c2dfdb0bf3",
    "id": "13205404970681503871",
    "replyCommentId" : 0,
    "content": "充满力量"
}

```

成功返回示例

```
{
    "message": "成功",
    "code": "1000",
    "data": null
}

```

返回数据：

| 参数名 | 类型 | 说明 |
| code | int | 1000成功，1001失败 |
| msg | String | 反馈信息 |

错误返回示例

```
{
    "message": "失败",
    "code": "1001",
    "data": null
}

```