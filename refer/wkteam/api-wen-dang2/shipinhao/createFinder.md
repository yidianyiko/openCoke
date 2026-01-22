- 创建视频号

## 创建视频号

[!DANGER]

- 视频号创建成功后可手机查看

请求URL：

- http://域名/createFinder

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| nickName | 是 | String | 视频号名称 |
| headImgUrl | 是 | String | 视频号头像 |

请求参数示例

```
{
    "wId":"2c7a5bf6-e23d-x-8f03-b90e844b539f",
    "nickName": "阿讯测试",
    "headImgUrl": "https://gimg2.182.40.194.50/image_search/src=http%3A%2F%2Fimg.jj20.com%2Fup%2Fallimg%2F1114%2F0G020114924%2F200G0114924-15-1200.jpg&refer=http%3A%2F%2Fimg.jj20.com&app=2002&size=f9999,10000&q=a80&n=0&g=0n&fmt=auto?sec=1657616129&t=f06cc1815b63173cca6f53a1f5e9f197"
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
| code | String | 1000成功1001失败 |
| msg | String | 反馈信息 |
| data | JSONObject |