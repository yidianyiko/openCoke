- 添加隐私设置

## 添加隐私设置

[!NOTE]

- 本接口设置成功后,效果立即生效，手机端展示会有延迟，可等待30S杀掉后台重启查看
- 本接口可调用多次，单次设置生效的都为一项

简要描述：

- 检测好友状态

请求URL：

- http://域名地址/userPrivacySettings

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| privacyType | 是 | int | 选择开启/关闭的某项4: 加我为朋友时需要验证7: 向我推荐通讯录朋友8: 添加我的方式 手机号25: 添加我的方式 微信号38: 添加我的方式 群聊39: 添加我的方式 我的二维码40: 添加我的方式 名片 |
| switchType | 是 | int | 1：关闭  2：开启 |

请求参数示例

```
{
    "wId": "01377f33-544c-4dc4-9184-bcbbcd3b05d0",
    "privacyType": 4,
    "switchType":2
}

```

成功返回示例

```
{

    "message": "成功",
    "code": "1000"

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