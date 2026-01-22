- 上传视频号视频

## 上传视频号视频

请求URL：

- http://域名/finderUpload

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| videoUrl | 是 | String | 视频链接 |
| imgUrl | 是 | String | 视频封面图片链接 |

请求参数示例

```
{
    "wId": "{{wId}}",
    "videoUrl":"https://pics6.182.40.194.50/feed/e824b899a9014c083a6e7dfa8df4e1047af4f4b0.mp4",
    "imgUrl": "https://pics6.182.40.194.50/feed/e824b899a9014c083a6e7dfa8df4e1047af4f4b0.jpeg@f_auto?token=fb7ac3bf714b8a6d05f4d1d8f44d7ca"
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "处理成功",
    "data": {
        "fileUrl": "http://wxapp.tc.qq.com/251/20302/stodownload?bizid=1023&dotrans=0&encfilekey=oibeqyX228riaCwo9STVsGLIBn9G5YG8Zn59wWGKtPKU7XeFey6Gmk5u2BLznEOJrqFUy37lHx0tFeRFc5SWn3wEic7G47PU6PjFia6lA35eRpS6FlNe4jhbMLfic3vY58FG7tSE1iaMA42ss&hy=SZ&idx=1&m=6e95f9d79588843ac259b780f0cbf20f&token=6xykWLEnztIy9Tia9kRZ3cECxpZ0O13rmJ2rkChlzDG9JDicybIofoLAsGVz9GTe9sqQ3ckuAbKr7M1dBMmptWZg&uzid=2",
        "thumbUrl": "http://wxapp.tc.qq.com/251/20350/stodownload?bizid=1023&dotrans=0&filekey=30350201010421301f020200fb0402535a0410cc9a86fb446c70f5ed6c16ca7754f4c102030090c2040d00000004627466730000000132&hy=SZ&m=cc9a86fb446c70f5ed6c16ca7754f4c1&storeid=56684c7b4000466e28399cc84000000fb00004f7e535a2f2f00115674d8bad&uzid=2",
        "mp4Identify": "5118be81f2de929d3c79fc8777732b43",
        "fileSize": 1315979,
        "thumbMd5": "cc9a86fb446c70f5ed6c16ca7754f4c1",
        "fileKey": "finder_upload_6764713041_zhangchuan2288"
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

返回数据：

| 参数名 | 类型 | 说明 |
| code | String | 1000成功1001失败 |
| msg | String | 反馈信息 |
| data | JSONObject |