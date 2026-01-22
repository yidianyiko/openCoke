- 获取收藏夹列表

# 获取收藏夹列表

简要描述：

- 获取收藏夹内容

请求URL：

- http://域名地址/weChatFavorites/favSync

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 微信实列ID |
| keyBuf | 是 | byte[] | 第一次传null,如果接口返回keyBuf第二次传keyBuf |

返回数据：

| 参数名 | 类型 | 说明 |
| code | string | 1000成功，1001失败 |
| msg | string | 反馈信息 |
| data |  |
| ret | int | 接口状态 0:成功 |
| favList | list | 收藏列表 |
| keyBuf | byte[] | 同步密钥 |
| continueFlag | int | 0:表示同步结束，1:表示还需要继续同步 |
| favId | int | 收藏标识 |
| type | int | 收藏类型 |
| updateTime | long | 收藏时间戳 |

请求参数示例

```
{
    "wId": "0000016e-c561-9bbd-0001-3dc796084901",
    "keyBuf":null
}

```

成功返回示例

```
{
    "message": "成功",
    "code": "1000",
    "data": {
        "ret": 0,
        "favList": [
            {
                "favId": 1,
                "type": 2,
                "updateTime": 1538560491
            },
            ......
        ],
        "keyBuf": null,
        "continueFlag": 0
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