- 获取标签列表

## 获取标签列表

简要描述：

- 获取标签列表

请求URL：

- http://域名地址/getContactLabelList

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |

请求参数示例

```
{
    "wId": "349be9b5-8734-45ce-811d-4e10ca568c67"
}

```

成功返回示例

```
{
    "message": "成功",
    "code": "1000",
    "data": [
        {
            "labelName": "看一看世界",
            "labelId": 3
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

返回数据：

| 参数名 | 类型 | 说明 |
| code | String | 1000成功1001失败 |
| msg | String | 反馈信息 |
| data | JSONObject |  |
| labelId | int | 标签标识 |
| labelName | int | 标签名称 |