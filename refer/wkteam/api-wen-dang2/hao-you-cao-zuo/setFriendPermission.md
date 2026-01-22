- 设置好友权限

# 设置好友权限

简要描述：

- 设置好友权限 本接口修改成功后 手机需退出后台，重新打开手机方可看到更改

请求URL：

- http://域名地址/setFriendPemission

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 微信实列ID |
| wcId | 是 | String | 好友微信id |
| type | 是 | int | 1:正常 2:仅聊天 |

返回数据：

| 参数名 | 类型 | 说明 |
| code | string | 1000成功，1001失败 |
| msg | string | 反馈信息 |
| data |

请求参数示例

```
{
    "wId": "f54179d3-26ea-46b5-8aa2-97f02e031a9b",
    "wcId":"LoChaX",
    "type":"1"
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