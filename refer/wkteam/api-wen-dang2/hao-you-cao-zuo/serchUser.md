- 搜索联系人

## 搜索联系人

简要描述：

- 搜索联系人

请求URL：

- http://域名地址/searchUser

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| wcId | 是 | String | 微信号/手机号 (不支持微信id搜索) |

请求参数示例

```
{
    "wId": "349be9b5-8734-45ce-811d-4e10ca568c67",
    "wcId": "k1455804517"
}

```

成功返回示例

```
{
    "message": "成功",
    "code": "1000",
    "data": {
        "nickName": "可可",
        "sex": 2,
        "v1": "v1_90c13d2bb0ff6bb85db28041af32ec2cc80194eac15c3ab6534d28c127a2270e802c06bba0a41a904423a01855870756@stranger",
        "userName": "v1_90c13d2bb0ff6bb85db28041af32ec2cc80194eac15c3ab6534d28c127a2270e802c06bba0a41a904423a01855870756@stranger",
        "v2": "v4_000b708f0b040000010000000000b1bda847bd5ff86a7d236cdee25e1000000050ded0b020927e3c97896a09d47e6e9e387eb23497cde91ca8c3d17dc5cfb3703eb5c81a9b0c457a9cafb398238b24ad0c0e060c43c6bd464ca15269a601c3dffa3da32a659c32e7e58eeee0b9ec7873c5a4828ce51992d917@stranger",
        "bigHead": "http://wx.qlogo.cn/mmhead/ver_1/R6ibiaIVLfEqxcDCCsOGN6ice3Z4pkLnYuV6M1VbYkicuCNATqBk3x2aDmx5uS0iaTvtrDWJlnSaPUwEexPTI67m3fRK4DvIHWIbe85bILNWPhC4/0",
        "smallHead": "http://wx.qlogo.cn/mmhead/ver_1/R6ibiaIVLfEqxcDCCsOGN6ice3Z4pkLnYuV6M1VbYkicuCNATqBk3x2aDmx5uS0iaTvtrDWJlnSaPUwEexPTI67m3fRK4DvIHWIbe85bILNWPhC4/132"
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

[!DANGER]

- 已是好友的话，v1 返回好友微信号 v2为空
- 搜索好友经常搭配添加好友接口使用，好友同意添加成功后会有回调，用户可根据本接口返回的v1和添加成功后回调返回的v1及wcid对应起来

| 参数名 | 类型 | 说明 |
| code | String | 1000成功1001失败 |
| msg | String | 反馈信息 |
| data | JSONObject |  |
| v1 | String | 添加好友凭证1（如果是好友 会返回微信id）唯一不变值好友添加成功后回调会返会此值 |
| sex | int | 性别 |
| userName | String | 微信号 |
| v2 | String | 添加好友凭证2 |
| bigHead | String | 大头像 |
| smallHead | String | 小头像 |