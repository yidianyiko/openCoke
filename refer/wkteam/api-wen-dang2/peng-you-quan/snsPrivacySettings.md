- 朋友圈权限设置

## 朋友圈权限设置

[!NOTE]

- 本接口设置成功后,效果立即生效，手机端展示会有延迟，可等待30S杀掉后台重启查看

请求URL：

- http://域名地址/snsPrivacySettings

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| type | 是 | int | 10: 允许好友查看全部朋友圈11：允许好友查看近半年12：允许好友查看近一个月13：允许好友查看近3天20：允许陌生人查看十条朋友圈21：不允许陌生人查看朋友圈 |

请求参数示例

```
{
     "wId": "b7ad08a6-77c2-4ad6-894a-29993b84c0e4",
     "type": 11
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