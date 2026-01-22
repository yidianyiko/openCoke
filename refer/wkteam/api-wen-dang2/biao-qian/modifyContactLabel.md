- 修改联系人标签

## 修改联系人标签

[!DANGER]

- 移除标签下的好友：
  把需移除的好友所有标签查出来（通讯录详情接口返回标签id，数据库需缓存），去掉想移出的标签id，labelIdList参数放进其他所有标签id。
- 增加标签新好友：
把需添加的好友所有标签查出来（通讯录详情接口返回标签id，数据库需缓存），labelIdList参数放进新标签id和原有所有标签id。
- 某个标签下批量添加/移除好友：
查出所有好友所在的标签id，每个和上方一样单独调用。

简要描述：

- 修改联系人标签

请求URL：

- http://域名地址/modifyContactLabel

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| wcId | 是 | String | 好友微信id |
| labelIdList | 是 | String | 标签标识，多个标签已 "，" 号分割 |

请求参数示例

```
{
    "wId": "349be9b5-8734-45ce-811d-4e10ca568c67",
    "wcId":"wxid_jg6e5v0b8bp322",
    "labelIdList":"1,2"
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