- 获取收藏夹内容

# 获取收藏夹内容

简要描述：

- 获取收藏详细信息

请求URL：

- http://域名地址/weChatFavorites/getFavItem

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 微信实列ID |
| favId | 是 | int | 收藏标识 |

返回数据：

| 参数名 | 类型 | 说明 |
| code | string | 1000成功，1001失败 |
| msg | string | 反馈信息 |
| data |  |
| object | xml | 收藏详情 |
| updateTime | long | 收藏时间戳 |

请求参数示例

```
{
    "wId": "0000016e-c561-9bbd-0001-3dc796084901",
    "favId":1
}

```

成功返回示例

```
{
    "message": "成功",
    "code": "1000",
    "data": {
        "favId": 1,
        "object": "<favitem type=\"2\"><source sourcetype=\"1\"><fromusr>wxid_gia1nwcgpobz22</fromusr><tousr>wxid_gia1nwcgpobz22</tousr></source><datalist count=\"1\"><dataitem datatype=\"2\" dataid=\"fe0f5bf7a6e734f10f4c94c1afe8c0e9\"><cdn_thumburl>30500201000449304702010002049c1da4d602033d11fd0204ed3e5b6502045b345cc6042265653239376562613737326138343233383430356466326462356330613266375f740204020027110201000400</cdn_thumburl><cdn_dataurl>304e020100044730450201000204359e277602033d14b90204717124b702045b4d9436042066386135656234396533636365373466353663376130323963393637353564370204020027110201000400</cdn_dataurl><cdn_thumbkey>f3698526452141a298c5a28f8fdf94e2</cdn_thumbkey><cdn_datakey>740d9b78211f47288213c9b6e6fd25b4</cdn_datakey><fullmd5>105062c3583d322f8336f0b38ba286ec</fullmd5><head256md5>5f0455eea82e20d7ba9a377d04aaa35a</head256md5><fullsize>18622</fullsize><thumbfullmd5>e961ae8fcecc36474f0d4a169fc5ade5</thumbfullmd5><thumbhead256md5>d41d8cd98f00b204e9800998ecf8427e</thumbhead256md5><thumbfullsize>12061</thumbfullsize><datadesc></datadesc><datatitle></datatitle></dataitem></datalist><recommendtaglist></recommendtaglist></favitem>",
        "updateTime": 1538560491
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