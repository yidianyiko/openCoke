- 删除收藏夹内容

# 删除收藏夹内容

简要描述：

- 删除收藏夹内容

请求URL：

- http://域名地址/weChatFavorites/delFavItem

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 微信实列ID |
| favId | 是 | int | 收藏标识 |

返回数据：

| 参数名 | 类型 | 说明 |
| code | string | 1000成功，1001失败 |
| msg | string | 反馈信息 |
| data |

请求参数示例

```
{
    "wId": "0000016e-c561-9bbd-0001-3dc796084901",
    "favId":1
}

```

成功返回示例

```
{
    "message": "成功",
    "code": "1000",
    "data": "收藏删除成功"
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