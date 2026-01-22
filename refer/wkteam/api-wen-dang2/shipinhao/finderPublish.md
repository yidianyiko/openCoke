- 发布视频号

## 发布视频号

请求URL：

- http://域名/finderPublish

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| myUserName | 是 | String | 自己的用户编码 |
| videoUrl | 是 | String | 视频链接 |
| videoThumbUrl | 是 | String | 封面链接 |
| videoWidth | 是 | int | 视频宽度 |
| videoHeight | 是 | int | 视频高度 |
| videoPlayLen | 是 | int | 视频播放时长，单位秒 |
| title | 是 | String | 标题 |
| topic | 是 | String[] | 话题 |
| videoCdn | 否 | JSONObject | 通过“上传视频号视频”接口获取 |
| videoCdn.fileUrl | 是 | String | 通过“上传视频号视频”接口获取 |
| videoCdn.thumbUrl | 是 | String | 通过“上传视频号视频”接口获取 |
| videoCdn.mp4Identify | 是 | String | 通过“上传视频号视频”接口获取 |
| videoCdn.fileSize | 是 | int | 通过“上传视频号视频”接口获取 |
| videoCdn.thumbMd5 | 是 | String | 通过“上传视频号视频”接口获取 |
| videoCdn.fileKey | 是 | String | 通过“上传视频号视频”接口获取 |

直发请求参数示例

```
{
    "wId": "{{wId}}",
    "myUserName": "v2_060000231003b20faec8c6e18f10c7d6c903ec3db0776955d3d97c6b329d6aa58693bcdb7ad1@finder",
    "videoUrl": "https://30&q-header-list=&q-url-param-list=&q-signature=e7a03064c2f701137570a525e6650631d8baf4be",
    "videoThumbUrl": "https://p92309022220191E400011D6391597E30B",
    "videoWidth": 1240,
    "videoHeight": 930,
    "videoPlayLen": 13,
    "title": "可爱吗？",
    "topic": [
        "#可爱",
        "#hhh"
    ]
}

```

使用“上传视频号视频”获取数据请求参数示例

```
{
    "wId": "{{wId}}",
    "myUserName": "v2_060000231003b20faec8c6e18f10c7d6c903ec3db0776955d3d97c6b329d6aa58693bcdb7ad1@finder",
    "myRoleType":3,
    "videoUrl": "",
    "videoThumbUrl": "",
    "videoWidth": 1240,
    "videoHeight": 930,
    "videoPlayLen": 13,
    "videoCdn": {
        "fileUrl": "http://wxapp.tc.qq.com/251/20302/stodownload?a=1&bizid=1023&dotrans=0&encfilekey=oibeqyX228riaCwo9STVsGLIBn9G5YG8Zn59wWGKtPKU7XeFey6Gmk5u2BLznEOJrqFUy37lHx0tFeRFc5SWn3wFichT2XyDjTHjOjzDDXk4DfMaBwxrjlB9gDrgiaPA3SqYMBmCsxQUp6E&hy=SZ&idx=1&m=6e95f9d79588843ac259b780f0cbf20f&token=cztXnd9GyrGDyHSr4tfFhrIZAEiaP5UUR4XdicQO9R2mT4KR2hmbPzozzC6CLYI280ibz3wvaVeCAKzic01dGVPECQ&upid=290150",
        "thumbUrl": "http://wxapp.tc.qq.com/251/20350/stodownload?m=cc9a86fb446c70f5ed6c16ca7754f4c1&filekey=30350201010421301f020200fb0402535a0410cc9a86fb446c70f5ed6c16ca7754f4c102030090c2040d00000004627466730000000132&hy=SZ&storeid=565253eba000b8def8399cc84000000fb00004f7e535a16a64bc1e046ae409&dotrans=0&bizid=1023",
        "mp4Identify": "f554da4964c2c64ad97dc9623f5daa5b",
        "fileSize": 1315979,
        "thumbMd5": "cc9a86fb446c70f5ed6c16ca7754f4c1",
        "fileKey": "finder_upload_8147263162_zhangchuan2288"
    },
    "title": "可爱吗？",
    "topic": [
        "#可爱",
        "#hhh"
    ]
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "视频号发布成功",
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