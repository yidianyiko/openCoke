- CDN资源下载

# CDN资源下载

简要描述：

- 下载资源类接口，例如小程序封面图，链接消息封面图，收藏夹中的加密的视频、图片、文件、笔记等

请求URL：

- http://域名地址/cdnDownFile

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | string | 登录实例标识 |
| cdnUrl | 是 | string | XML获取 |
| aeskey | 是 | string | XML获取 |
| fileType | 是 | int | 1：高清图片  2：常规图片  3：缩略图  4：视频 5：文件图片如果下载失败，建议尝试其他几种，并不是所有图片都有高清、常规、缩略 |
| fileName | 是 | string | 资源全称（例 'test.png'） |
| totalSize | 是 | int | XML中的length |

返回数据：

| 参数名 | 类型 | 说明 |
| code | string | 1000成功，1001失败 |
| msg | string | 反馈信息 |

请求参数示例

```
{
  "wId": "59c7a5b1-3c01-480c-828c-46eade762287",
  "cdnUrl": "307f02010004783076020100020464e5eb6502033d14b90204ac612fb70204611399240451777875706c6f61645f7a68616e67636875616e32323838584d755078697958744f5f313632383637343334305f34656464666331302d613337622d343439382d393934372d6431663230333633376237640204011818020201000400",
  "aeskey": "4eddfc10-a37b-4498-9947-d1f203637b7d",
  "fileType":3,
  "fileName": "test.jpg",
  "totalSize": 206249
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "处理成功",
    "data": {
        "url": "http://xdkj-enterprise.oss-cn-beijing.aliyuncs.com/20210812/cab24cf9-867c-486b-bef4-d22bef89d444-test.jpg?Expires=1629350242&OSSAccessKeyId=LTAI4G5VB9BMxMDV14c6USjt&Signature=fWvkoKlE%2F4iIMxbN99DBGJDKRjA%3D"
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