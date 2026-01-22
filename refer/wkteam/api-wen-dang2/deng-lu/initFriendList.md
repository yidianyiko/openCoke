- 初始化通讯录列表

## 初始化通讯录列表

简要描述：

- 初始化通讯录列表

请求URL：

- http://域名地址/initAddressList

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |

[!DANGER]小提示：

- 本接口为耗时接口(返回在10s-3min之间)，建议仅每次登录成功后调用一次至本地数据库，本接口和获取通讯录列表接口为组合接口

请求参数示例

```
{
    "wId": "6a696578-16ea-4edc-ac8b-e609bca39c69"
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
| code | string | 1000成功、1001失败 |
| msg | string | 反馈信息 |
| data | JSONObject | 无 |