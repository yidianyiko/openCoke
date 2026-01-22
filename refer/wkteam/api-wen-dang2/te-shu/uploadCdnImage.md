- CDN图片上传

# CDN图片上传

简要描述：

- 图片上传接口，主要应用于动态替换小程序封面图（更改XML中的cdnkey相关信息）+ 多微信发同内容场景，动态组装转发接口xml发送

请求URL：

- http://域名地址/uploadCdnImage

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | string | 登录实例标识 |
| content | 是 | string | 图片url链接 |

返回数据：

| 参数名 | 类型 | 说明 |
| code | string | 1000成功，1001失败 |
| msg | string | 反馈信息 |
| cdnUrl | string | 图片cdn信息（用于自定义小程序图片参数） |
| aesKey | string | 图片key信息（用于自定义小程序图片参数） |
| hdLength | string | 图片大小（用于自定义小程序图片参数） |

请求参数示例

```
{
    "wId": "0000016e-63eb-f319-0001-ed01076abf1f",
    "content": "http://photocdn.sohu.com/20120323/Img338614056.jpg"
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "发送图片消息成功",
    "data": {
        "cdnUrl": "307b0201000474307202010002041b9042eb02033d14b902045412607102046113de29044d777875706c6f61645f636861745f7365766f6e4b4f4a494d70615456765f313632383639323030395f32656631613130312d613939392d346161622d626263352d3765363034383262633135350204011818020201000400",
        "aesKey": "52efd887fcfdad1d71c29d0129daaabd",
        "hdLength": 173475
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