- 批量下线微信号

# 批量下线微信号

简要描述：

- 下线某个或某些已登录的微信（假如出现登录数量已满，则调用本接口释放）

请求URL：

- http://域名地址/member/offline

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| account | 是 | string | 账号 |
| wcIds | 是 | list | 须下线的微信id |

返回数据：

| 参数名 | 类型 | 说明 |
| code | string | 1000成功，1001失败 |
| msg | string | 反馈信息 |
| data |

请求参数示例

```
{

   "account": "1234567890",
   "wcIds": ["wxid_1r6wafuhou3e22","wxid_wl9qchkanp9u22"]

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