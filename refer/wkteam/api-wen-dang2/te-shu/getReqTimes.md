- 查询接口调用次数

# 查询接口调用次数

简要描述：

- 查看服务器中所有用户接口调用次数

请求URL：

- http://域名地址/getReqTimes

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：无

返回数据：

| 参数名 | 类型 | 说明 |
| code | string | 1000成功，1001失败 |
| msg | string | 反馈信息 |
| account | string | 开发者账号 |
| nickName | string | 微信昵称 |
| wcId | string | 微信id |
| times | string | 接口调用次数 |
| wid | string | 登录实例标识 |

请求参数示例

```
空

```

成功返回示例

```
{
    "code": "1000",
    "message": "处理成功",
    "data": [
        {
            "account": "18733333212",
            "nickName": "转发朋友圈专用号勿删拉黑",
            "wcId": "wxid_683evhfc922",
            "times": 1058585,
            "wid": "e64899c6-f4ab-4a37-f4-cf0bb688461b"
        },
        {
            "account": "18733333212",
            "nickName": "大拿@联萌(此号转发朋友圈勿删除）",
            "wcId": "wxid_0xnbrfacqv22",
            "times": 853637,
            "wid": "c38e9946-25be-4c10-9704e8da31db171"
        }
    ]
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