- 弹框登录

## 弹框登录

简要描述：

- 二次登录

请求URL：

- http://域名地址/secondLogin

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

[!DANGER]

- 本接口是微信掉线后，再次登录时候调用，本接口效果是无需扫码，手机会直接弹出登录弹框确认。
- 本接口非100%成功，若返回失败，则仍需传wcId调用第二步接口扫码登录，
- 若手机点击了取消登录，或被微信风控踢下线，或24H首夜掉线，或手机操作时间过长无反应则返回失败

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wcId | 是 | string | 微信id（登录接口返回的wcId） |
| ttuid | 否 | string | 网络类型2，若上次登录使用ttuid，本参数则必传，反之则不传 |
| aid | 否 | string |  | 网络类型4，若上次登录使用的是aid，请保证aid工具打开即可，此参数可不传】 |

返回数据：

| 参数名 | 类型 | 说明 |
| code | string | 1000成功，1001失败 |
| msg | string | 反馈信息 |
| data |
| wId | string | 登录实例标识,登录成功后wId会变更，记得更新 |
| wcId | string | 微信id |
| nickName | string | 昵称 |
| headUrl | string | 头像url |
| wAccount | string | 手机上显示的微信号 |
| sex | int | 性别 |
| status | string | 3 扫码登录成功 |

请求参数示例

```
{

 "wcId": "wxid_gia1nwcgpobz22"
}

```

成功返回示例

```
{
    "message": "成功",
    "code": "1000",
    "data": {
        "wcId": "wxid_ylxtflcg0p8b22",
        "wAccount": "hirsi520",
        "country": "CN",
        "wId": "c7fcd475-3c86-4061-ba95-aaae52bf9620",
        "city": "Nanjing",
        "signature": "E云客服对接，api 系统，大家有问题可以找我咨询呀",
        "nickName": "售前客服-小诺 (工作日9:00-18:00)",
        "sex": 2,
        "headUrl": "http://wx.qlogo.cn/mmhead/ver_1/71icIciaZ1RvFpIJUGp6pCI6Uydndbib74FyUY6pPrEKO1F4cVTgfx5QjnoShlGZamsMicOYWccSqUicZ1LsKtQjtr5icyQiau5aAiaLafMPo9e1vQU/0",
        "smallHeadImgUrl": "http://wx.qlogo.cn/mmhead/ver_1/71icIciaZ1RvFpIJUGp6pCI6Uydndbib74FyUY6pPrEKO1F4cVTgfx5QjnoShlGZamsMicOYWccSqUicZ1LsKtQjtr5icyQiau5aAiaLafMPo9e1vQU/132",
        "status": 3
    }
}

```

错误返回示例

```
{
    "message": "系统失败,请重试",
    "code": "1001",
    "data": null
}

{
    "message": "成功",
    "code": "1000",
    "data": {
        "message": "二次登录失败，请重新扫码登录",
        "code": "1001",
        "data": null
    }
}

```