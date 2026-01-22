- 删除某条朋友圈的某条评论

## 删除某条朋友圈的某条评论

简要描述：

- 删除某条朋友圈的某条评论

请求URL：

- http://域名地址/snsCommentDel

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| id | 是 | String | 朋友圈id |
| commentId | 是 | int | 评论id |

请求参数示例

```
{
    "wId": "349be9b5-8734-45ce-811d-4e10ca568c67",
    "id": "13341784993555026081",
    "commentId": "227"
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