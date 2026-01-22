- 修改好友备注

# 修改好友备注

简要描述：

- 修改好友备注

请求URL：

- http://域名地址/modifyRemark

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | string | 登录实例标识 |
| wcId | 是 | string | 好友微信id |
| remark | 是 | string | 好友备注 |

返回数据：

| 参数名 | 类型 | 说明 |
| code | string | 1000成功，1001失败 |
| msg | string | 反馈信息 |

请求参数示例

```
{
   "wId": "0000016f-a2aa-9089-0001-32dbe7c94132",
   "wcId": "wxid_ao4ziqc2g9b922",
   "remark": "备注"
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