- 搜索视频号

## 搜索视频号

请求URL：

- http://域名/newSearchFinder

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| content | 是 | String | 搜索内容 |
| type | 是 | int | 搜索类型0:全部1:搜索用户10:搜索视频（ps：不同类型，返回JSON不同） |
| filter | 是 | int | 筛选0:不限1:最新2:朋友赞过 |
| page | 是 | int | 页码，首次传1，后续自行累加 |
| offset | 是 | int | 偏移量，首次传0，后续传接口返回的offset |
| cookie | 否 | String | cookie信息，首次传空，后续传接口返回的cookie |
| searchId | 否 | String | 搜索信息，首次传空，后续传接口返回的searchId |

请求参数示例

```
{
    "wId": "2c7a5bf6-e23d-x-8f03-b90e844b539f",
    "content": "中国",
    "type": 0,
    "filter": 0,
    "page": 1,
    "offset": 0,
    "cookie": "",
    "searchId": ""
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "处理成功",
    "data": {
        "cookie": "{\"box_offset\":0,\"businessType\":14,\"cookies_buffer\":\"UhoIexABGA4iBuS4reWbvVABeAiCAQUQBaIBAA==\",\"doc_offset\":0,\"dup_bf\":\"\",\"isHomepage\":0,\"page_cnt\":1,\"query\":\"中国\",\"scene\":123}\n",
        "searchId": "416754344366039934",
        "offset": 8,
        "authInfos": [],
        "videoInfos": [
            {
                "items": [
                    {
                        "dateTime": "3天前",
                        "docId": "14212057401545988355",
                        "duration": "08:09",
                        "image": "http://wxapp.tc.qq.com/251/20304/stodownload?encfilekey=oibeqyX228riaCwo9STVsGLPj9UYCicgttvia8Me3Iw7dE8gXOjUzSmu6r8ofw8cYtReGJEB117XjBrDOj5RP2osD7Ew7vxk6T5oBsTmbTU4k6COicM9jEAhia0LIvDjoOXMNdPNAZicjEKeKw&bizid=1023&dotrans=0&hy=SH&idx=1&m=94b80bae11184583d673d6149ce6d444&token=x5Y29zUxcibCadRELU5qibElZGLZcyHZ4ACWfJseChEibnLqlbEjCt7ZkHbd9A4dC5p",
                        "imageData": {
                            "height": 1088,
                            "width": 1920,
                            "url": "http://wxapp.tc.qq.com/251/20304/stodownload?encfilekey=oibeqyX228riaCwo9STVsGLPj9UYCicgttvia8Me3Iw7dE8gXOjUzSmu6r8ofw8cYtReGJEB117XjBrDOj5RP2osD7Ew7vxk6T5oBsTmbTU4k6COicM9jEAhia0LIvDjoOXMNdPNAZicjEKeKw&bizid=1023&dotrans=0&hy=SH&idx=1&m=94b80bae11184583d673d6149ce6d444&token=x5Y29zUxcibCadRELU5qibElZGLZcyHZ4ACWfJseChEibnLqlbEjCt7ZkHbd9A4dC5p"
                        },
                        "likeNum": "10万+",
                        "pubTime": 1694209265,
                        "reportId": "14212057401545988355:feed:0",
                        "showType": null,
                        "source": {
                            "iconUrl": "https://wx.qlogo.cn/finderhead/ver_1/OGtb2O7uCQZiafCiazicARJTpmSYpiaUCu1fMR3sn4zcAj78PEyUYvKhnsWuHS8HocibyqepqsOPMF187u610rxXRXdianLcPpEwYqV2NBRia36cao/132",
                            "mark": [
                                "https://dldir1v6.qq.com/weixin/checkresupdate/auth_icon_level3_2e2f94615c1e4651a25a7e0446f63135.png"
                            ],
                            "title": "雪山在那里"
                        },
                        "jumpInfo": {
                            "extInfo": "{\"behavior\":[\"report_feed_read\",\"allow_pull_top\",\"allow_infinite_top_pull\"],\"encryptedObjectId\":\"export/UzFfAgtgekIEAQAAAAAAInsX9AtMcwAAAAstQy6ubaLX4KHWvLEZgBPE14EAKhcxDfiGzNPgMIrQJV4ESYEKopnVZhYmR6Nt\",\"feedFocusChangeNotify\":true,\"feedNonceId\":\"11155216971528673864\",\"getRelatedList\":true,\"reportExtraInfo\":\"{\\\"report_json\\\":\\\"\\\"}\\n\",\"reportScene\":14,\"requestScene\":13,\"sessionId\":\"CIOy8JSH3dedxQEI_JDcv8yZ86DFAQjEsLS1ttCNlcUBCJ-wtJ64kIjaxAEIpLDIh5fI1-bEAQj4kczthsffocUBCJew8Pm6n6aexQEI2LDo_K-jyKHFAQjMsKSvvomM9sQBCOeRzI_jhtSVxQEIlLKo-MSU4aHFARD-xqf04_um5AUqBuS4reWbvTAAOICAgICAgAJAAVCft7KBBQ..\"}\n",
                            "feedId": "14212057401545988355",
                            "jumpType": 9
                        },
                        "title": "...父母需在孩子陪同下观看。这里是<em class=\"highlight\">中国</em>。",
                        "videoUrl": "https://findermp.video.qq.com/251/20302/stodownload?encfilekey=6xykWLEnztKcKCJZcV0rWCM8ua7DibZkibqXGfPxf5lrrNgPZMFicGq71GHhsibpJbcUe2mhY6SADicbuwrIP3Pk4doGYFhyticbsuZXHvNHW2A1tzA91Ku8QBKtCZ21dyZYe7t1Gjj5RKw2HFibOF9Kx5mYtRDR0LHz1Ukp7uEUEYdxKY&a=1&bizid=1023&dotrans=0&hy=SH&idx=1&m=691ea000eff81fcc9c6521f1a16dd0be&upid=500250&partscene=4&X-snsvideoflag=W21&token=AxricY7RBHdUkQSDFU11VLDP6QTzY8dtT7CE8ssJelMicM4mPLobWsBiaQLnn8LPsJTrePhjL3nicEU"
                    }
                ],
                "boxId": "0x80000000000-1-14212057401545988355",
                "type": 86,
                "subType": 1,
                "totalCount": 270
            },
            {
                "items": [
                    {
                        "dateTime": "",
                        "docId": "4791196579134016048",
                        "duration": "",
                        "image": "",
                        "imageData": {
                            "height": 0,
                            "width": 0,
                            "url": ""
                        },
                        "likeNum": null,
                        "pubTime": 0,
                        "reportId": "",
                        "showType": null,
                        "source": {
                            "iconUrl": "http://p.qpic.cn/hottopic/0/1590389140e56978cf65585a00b2c57642dd008ab6/0",
                            "mark": null,
                            "title": "搜狗百科小程序"
                        },
                        "jumpInfo": {
                            "extInfo": "",
                            "feedId": "",
                            "jumpType": 2
                        },
                        "title": "<em class=\"highlight\">中国</em> - 百科",
                        "videoUrl": ""
                    }
                ],
                "boxId": "0x80000000-0-4791196579134016048",
                "type": 16777728,
                "subType": 0,
                "totalCount": 1
            },
            {
                "items": [
                    {
                        "dateTime": "18小时前",
                        "docId": "14213867078858246268",
                        "duration": "00:13",
                        "image": "http://wxapp.tc.qq.com/251/20304/stodownload?encfilekey=rjD5jyTuFrIpZ2ibE8T7YmwgiahniaXswqziceZZHuetsMbO0HYPvqOlJ7VVplVnlkIbQibGia1s6sUvOHAYrblNU6YFkEZ6Z8yu1fib6HwT0XNROZfXiaUyWQCFTw&bizid=1023&dotrans=0&hy=SH&idx=1&m=&scene=0&token=cztXnd9GyrFAja2VYvGJOv3oVIqqZfDUbFLA9s2E521Qm5zic3920C1bDAiaaRXsoN",
                        "imageData": {
                            "height": 1920,
                            "width": 1080,
                            "url": "http://wxapp.tc.qq.com/251/20304/stodownload?encfilekey=rjD5jyTuFrIpZ2ibE8T7YmwgiahniaXswqziceZZHuetsMbO0HYPvqOlJ7VVplVnlkIbQibGia1s6sUvOHAYrblNU6YFkEZ6Z8yu1fib6HwT0XNROZfXiaUyWQCFTw&bizid=1023&dotrans=0&hy=SH&idx=1&m=&scene=0&token=cztXnd9GyrFAja2VYvGJOv3oVIqqZfDUbFLA9s2E521Qm5zic3920C1bDAiaaRXsoN"
                        },
                        "likeNum": "317",
                        "pubTime": 1694424996,
                        "reportId": "14213867078858246268:feed:0",
                        "showType": null,
                        "source": {
                            "iconUrl": "http://wx.qlogo.cn/mmhead/Q3auHgzwzM6icZCTWRZrNnQa9vOJmZ9ftLOztwJSXiaD3CBjiaO7NcGmw/132",
                            "mark": [
                                "https://dldir1v6.qq.com/weixin/checkresupdate/icons_filled_channels_authentication_enterprise_a2658032368245639e666fb11533a600.png"
                            ],
                            "title": "新华社电视"
                        },
                        "jumpInfo": {
                            "extInfo": "{\"behavior\":[\"report_feed_read\",\"allow_pull_top\",\"allow_infinite_top_pull\"],\"encryptedObjectId\":\"export/UzFfAgtgekIEAQAAAAAACgQI9q2TyAAAAAstQy6ubaLX4KHWvLEZgBPEqKMsAVx1KcWGzNPgMIql2-qktfOXJpQypSZWUver\",\"feedFocusChangeNotify\":true,\"feedNonceId\":\"8054243567951799894\",\"getRelatedList\":true,\"reportExtraInfo\":\"{\\\"report_json\\\":\\\"\\\"}\\n\",\"reportScene\":14,\"requestScene\":13,\"sessionId\":\"CIOy8JSH3dedxQEI_JDcv8yZ86DFAQjEsLS1ttCNlcUBCJ-wtJ64kIjaxAEIpLDIh5fI1-bEAQj4kczthsffocUBCJew8Pm6n6aexQEI2LDo_K-jyKHFAQjMsKSvvomM9sQBCOeRzI_jhtSVxQEIlLKo-MSU4aHFARD-xqf04_um5AUqBuS4reWbvTAAOICAgICAgAJAAVCft7KBBQ..\"}\n",
                            "feedId": "14213867078858246268",
                            "jumpType": 9
                        },
                        "title": "平安就好！<em class=\"highlight\">中国</em>援摩医生成功救助“地震宝宝”  \n",
                        "videoUrl": "https://findermp.video.qq.com/251/20302/stodownload?encfilekey=Cvvj5Ix3eewK0tHtibORqcsqchXNh0Gf3sJcaYqC2rQAlAtVPHnBRJncljibDbia3HRRoAIcVu9T5BDqsS822zGbrTfsiawAIKkZFjYzj1NDXlt97rLFlz3w6pfLicumGDZeO&bizid=1023&dotrans=0&hy=SH&idx=1&m=&upid=0&partscene=4&X-snsvideoflag=WT98&token=x5Y29zUxcibDuvYLQPf5C2rGMLSLxKOUlukc8xYCp6m9iaEXibGrm03Q23vrCKeaUQXkbmUSKz13pw"
                    }
                ],
                "boxId": "0x80000000000-1-14213867078858246268",
                "type": 86,
                "subType": 1,
                "totalCount": 270
            },
            {
                "items": [
                    {
                        "dateTime": "",
                        "docId": "中国国旗",
                        "duration": "",
                        "image": "",
                        "imageData": {
                            "height": 0,
                            "width": 0,
                            "url": ""
                        },
                        "likeNum": null,
                        "pubTime": 0,
                        "reportId": "%E4%B8%AD%E5%9B%BD%E5%9B%BD%E6%97%97:hint:500415",
                        "showType": null,
                        "source": {
                            "iconUrl": "",
                            "mark": null,
                            "title": ""
                        },
                        "jumpInfo": {
                            "extInfo": "",
                            "feedId": "",
                            "jumpType": 0
                        },
                        "title": "",
                        "videoUrl": ""
                    },
                    {
                        "dateTime": "",
                        "docId": "五星红旗",
                        "duration": "",
                        "image": "",
                        "imageData": {
                            "height": 0,
                            "width": 0,
                            "url": ""
                        },
                        "likeNum": null,
                        "pubTime": 0,
                        "reportId": "%E4%BA%94%E6%98%9F%E7%BA%A2%E6%97%97:hint:601180",
                        "showType": null,
                        "source": {
                            "iconUrl": "",
                            "mark": null,
                            "title": ""
                        },
                        "jumpInfo": {
                            "extInfo": "",
                            "feedId": "",
                            "jumpType": 0
                        },
                        "title": "",
                        "videoUrl": ""
                    },
                    {
                        "dateTime": "",
                        "docId": "中国国土面积",
                        "duration": "",
                        "image": "",
                        "imageData": {
                            "height": 0,
                            "width": 0,
                            "url": ""
                        },
                        "likeNum": null,
                        "pubTime": 0,
                        "reportId": "%E4%B8%AD%E5%9B%BD%E5%9B%BD%E5%9C%9F%E9%9D%A2%E7%A7%AF:hint:668959",
                        "showType": null,
                        "source": {
                            "iconUrl": "",
                            "mark": null,
                            "title": ""
                        },
                        "jumpInfo": {
                            "extInfo": "",
                            "feedId": "",
                            "jumpType": 0
                        },
                        "title": "",
                        "videoUrl": ""
                    },
                    {
                        "dateTime": "",
                        "docId": "中国纪录片",
                        "duration": "",
                        "image": "",
                        "imageData": {
                            "height": 0,
                            "width": 0,
                            "url": ""
                        },
                        "likeNum": null,
                        "pubTime": 0,
                        "reportId": "%E4%B8%AD%E5%9B%BD%E7%BA%AA%E5%BD%95%E7%89%87:hint:340841",
                        "showType": null,
                        "source": {
                            "iconUrl": "",
                            "mark": null,
                            "title": ""
                        },
                        "jumpInfo": {
                            "extInfo": "",
                            "feedId": "",
                            "jumpType": 0
                        },
                        "title": "",
                        "videoUrl": ""
                    },
                    {
                        "dateTime": "",
                        "docId": "中国消防",
                        "duration": "",
                        "image": "",
                        "imageData": {
                            "height": 0,
                            "width": 0,
                            "url": ""
                        },
                        "likeNum": null,
                        "pubTime": 0,
                        "reportId": "%E4%B8%AD%E5%9B%BD%E6%B6%88%E9%98%B2:hint:553702",
                        "showType": null,
                        "source": {
                            "iconUrl": "",
                            "mark": null,
                            "title": ""
                        },
                        "jumpInfo": {
                            "extInfo": "",
                            "feedId": "",
                            "jumpType": 0
                        },
                        "title": "",
                        "videoUrl": ""
                    }
                ],
                "boxId": "0x800-3-0",
                "type": 24,
                "subType": 3,
                "totalCount": 0
            },
            {
                "items": [
                    {
                        "dateTime": "9天前",
                        "docId": "14207227912484886596",
                        "duration": "00:52",
                        "image": "http://wxapp.tc.qq.com/251/20304/stodownload?encfilekey=S7s6ianIic0ia4PicKJSfB8EjyjpQibPUAXolmkD2enuo8BLbH4njzLUABgeZYVCqdlYT62vDKcOEqia4KocUy6J43H2dScOFlSgZ04j8wjmW8tAwX4aR3uhicxgQ&bizid=1023&dotrans=0&hy=SH&idx=1&m=&scene=0&token=x5Y29zUxcibA8OUawCN97XiafTrhMEgMPfcbZjQeUohvUt1p5a7ddzfFIR2iaBDMdKx",
                        "imageData": {
                            "height": 1704,
                            "width": 1080,
                            "url": "http://wxapp.tc.qq.com/251/20304/stodownload?encfilekey=S7s6ianIic0ia4PicKJSfB8EjyjpQibPUAXolmkD2enuo8BLbH4njzLUABgeZYVCqdlYT62vDKcOEqia4KocUy6J43H2dScOFlSgZ04j8wjmW8tAwX4aR3uhicxgQ&bizid=1023&dotrans=0&hy=SH&idx=1&m=&scene=0&token=x5Y29zUxcibA8OUawCN97XiafTrhMEgMPfcbZjQeUohvUt1p5a7ddzfFIR2iaBDMdKx"
                        },
                        "likeNum": "5万",
                        "pubTime": 1693633545,
                        "reportId": "14207227912484886596:feed:0",
                        "showType": null,
                        "source": {
                            "iconUrl": "http://wx.qlogo.cn/mmhead/Q3auHgzwzM4z64koK7VE0lpycmRhDENFv3BLW10adic0icmh4aTM6tMA/132",
                            "mark": [
                                "https://dldir1v6.qq.com/weixin/checkresupdate/icons_filled_channels_authentication_enterprise_a2658032368245639e666fb11533a600.png"
                            ],
                            "title": "中国政府网"
                        },
                        "jumpInfo": {
                            "extInfo": "{\"behavior\":[\"report_feed_read\",\"allow_pull_top\",\"allow_infinite_top_pull\"],\"encryptedObjectId\":\"export/UzFfAgtgekIEAQAAAAAAnLIQjGLE3AAAAAstQy6ubaLX4KHWvLEZgBPEkINECyY8V_CGzNPgMIo-e71qpvDe8KCwparuPFUb\",\"feedFocusChangeNotify\":true,\"feedNonceId\":\"12911466036332020329\",\"getRelatedList\":true,\"reportExtraInfo\":\"{\\\"report_json\\\":\\\"\\\"}\\n\",\"reportScene\":14,\"requestScene\":13,\"sessionId\":\"CIOy8JSH3dedxQEI_JDcv8yZ86DFAQjEsLS1ttCNlcUBCJ-wtJ64kIjaxAEIpLDIh5fI1-bEAQj4kczthsffocUBCJew8Pm6n6aexQEI2LDo_K-jyKHFAQjMsKSvvomM9sQBCOeRzI_jhtSVxQEIlLKo-MSU4aHFARD-xqf04_um5AUqBuS4reWbvTAAOICAgICAgAJAAVCft7KBBQ..\"}\n",
                            "feedId": "14207227912484886596",
                            "jumpType": 9
                        },
                        "title": "习近平：<em class=\"highlight\">中国</em>愿同各国各方一道，携手推动世界经济走上持续复苏轨道。（转自：央视新闻）",
                        "videoUrl": "https://findermp.video.qq.com/251/20302/stodownload?encfilekey=Cvvj5Ix3eewK0tHtibORqcsqchXNh0Gf3sJcaYqC2rQAIAsEjiciatZ0wicd8TicicB9hUWUjFGxyVFbOhVC5d5RN03Ky5j2lQu7Ofvl4m2VU9qV1CsNvF6cl1h95TA1uLpbcN&bizid=1023&dotrans=0&hy=SH&idx=1&m=&upid=0&partscene=4&X-snsvideoflag=WT68&token=x5Y29zUxcibDuvYLQPf5C2r8ptXtWHXT79L25QC76LlW1QiaxSQJ8E5fCyXpiaCwDsWgTxV2LeJ4Gs"
                    }
                ],
                "boxId": "0x80000000000-1-14207227912484886596",
                "type": 86,
                "subType": 1,
                "totalCount": 270
            },
            {
                "items": [
                    {
                        "dateTime": "2个月前",
                        "docId": "14173989676465854495",
                        "duration": "04:25",
                        "image": "http://wxapp.tc.qq.com/251/20350/stodownload?encfilekey=WTva9YVXqXcSUicrMCercmDHmKYPBXC7e5cX9BxwFGstJUrVGf3OEyfwXBmY2m5khAVODvBtqunkmcoTqgsJiaUz2mDjD2PlBpaibyviazwQtngNPKrOEgWULHE95FppG1dUaRI7dB04lcg&bizid=1023&dotrans=0&hy=SH&idx=1&m=07e87a9b0ba96892e7cef94fb6ca9433&token=cztXnd9GyrGqKjnmm8EjsCicYxrtY6NWAUCKJxJyN5PNWiaugtl2jT0DHunEBpAkiba",
                        "imageData": {
                            "height": 1080,
                            "width": 1920,
                            "url": "http://wxapp.tc.qq.com/251/20350/stodownload?encfilekey=WTva9YVXqXcSUicrMCercmDHmKYPBXC7e5cX9BxwFGstJUrVGf3OEyfwXBmY2m5khAVODvBtqunkmcoTqgsJiaUz2mDjD2PlBpaibyviazwQtngNPKrOEgWULHE95FppG1dUaRI7dB04lcg&bizid=1023&dotrans=0&hy=SH&idx=1&m=07e87a9b0ba96892e7cef94fb6ca9433&token=cztXnd9GyrGqKjnmm8EjsCicYxrtY6NWAUCKJxJyN5PNWiaugtl2jT0DHunEBpAkiba"
                        },
                        "likeNum": "3.2万",
                        "pubTime": 1689671239,
                        "reportId": "14173989676465854495:feed:0",
                        "showType": null,
                        "source": {
                            "iconUrl": "http://wx.qlogo.cn/mmhead/Q3auHgzwzM7fuNOe6Mepx3orIoHZG4C5h38TW4RsbWOsDohUCFb3LQ/132",
                            "mark": [
                                "https://dldir1v6.qq.com/weixin/checkresupdate/icons_filled_channels_authentication_enterprise_a2658032368245639e666fb11533a600.png"
                            ],
                            "title": "时报热点"
                        },
                        "jumpInfo": {
                            "extInfo": "{\"behavior\":[\"report_feed_read\",\"allow_pull_top\",\"allow_infinite_top_pull\"],\"encryptedObjectId\":\"export/UzFfAgtgekIEAQAAAAAA3QgEfmAp2wAAAAstQy6ubaLX4KHWvLEZgBPEy4NEICh8Ur-HzNPgMIq-WhHkJaY5rPcTdzXRgbaL\",\"feedFocusChangeNotify\":true,\"feedNonceId\":\"13863296488069395237\",\"getRelatedList\":true,\"reportExtraInfo\":\"{\\\"report_json\\\":\\\"\\\"}\\n\",\"reportScene\":14,\"requestScene\":13,\"sessionId\":\"CIOy8JSH3dedxQEI_JDcv8yZ86DFAQjEsLS1ttCNlcUBCJ-wtJ64kIjaxAEIpLDIh5fI1-bEAQj4kczthsffocUBCJew8Pm6n6aexQEI2LDo_K-jyKHFAQjMsKSvvomM9sQBCOeRzI_jhtSVxQEIlLKo-MSU4aHFARD-xqf04_um5AUqBuS4reWbvTAAOICAgICAgAJAAVCft7KBBQ..\"}\n",
                            "feedId": "14173989676465854495",
                            "jumpType": 9
                        },
                        "title": "...你们才是麻烦制造者\n<em class=\"highlight\">中国</em>常驻联合国代表张军13日在联合国安理会公开会上，就日前北约维尔纽斯峰会公报污蔑抹黑<em class=\"highlight\">中国</em>予以严厉驳斥。",
                        "videoUrl": "https://findermp.video.qq.com/251/20302/stodownload?encfilekey=Cvvj5Ix3eewK0tHtibORqcsqchXNh0Gf3sJcaYqC2rQCoFfdy9ySVnrwx8biaAk7Zpb2Un1iaibra1cLdKzr7UJtLVjrrBZVgH5JdRE56Rq8TmicRBJyCGBew8hnI4K32iclBx&bizid=1023&dotrans=0&hy=SH&idx=1&m=&partscene=4&X-snsvideoflag=WT67&token=x5Y29zUxcibDuvYLQPf5C2lqeSYTxBibGm4It2KLw2q49XiaEOCdKVDnlZibZddDk5xCa94e7mhdPTw"
                    }
                ],
                "boxId": "0x80000000000-1-14173989676465854495",
                "type": 86,
                "subType": 1,
                "totalCount": 270
            },
            {
                "items": [
                    {
                        "dateTime": "2个月前",
                        "docId": "14181094436820359204",
                        "duration": "01:15",
                        "image": "http://wxapp.tc.qq.com/251/20304/stodownload?encfilekey=oibeqyX228riaCwo9STVsGLPj9UYCicgttv8ncLu2tpCG4H2hib1z6D4WZJia0A7CqOo29yLHouiaGuRAYOLRvykKqAzZCxzjRjLmPhdMLSwG52GL3HjSuMpUgSprZkAHQHyp1LSsJuGo6qCA&bizid=1023&dotrans=0&hy=SH&idx=1&m=ba338dbc90c69418f32dec93d24d5375&token=cztXnd9GyrG0x7aBXH688SyLXsuKraQU02BBfpj2SCUVFyns5hldpAOc9tME9kOW",
                        "imageData": {
                            "height": 1920,
                            "width": 1080,
                            "url": "http://wxapp.tc.qq.com/251/20304/stodownload?encfilekey=oibeqyX228riaCwo9STVsGLPj9UYCicgttv8ncLu2tpCG4H2hib1z6D4WZJia0A7CqOo29yLHouiaGuRAYOLRvykKqAzZCxzjRjLmPhdMLSwG52GL3HjSuMpUgSprZkAHQHyp1LSsJuGo6qCA&bizid=1023&dotrans=0&hy=SH&idx=1&m=ba338dbc90c69418f32dec93d24d5375&token=cztXnd9GyrG0x7aBXH688SyLXsuKraQU02BBfpj2SCUVFyns5hldpAOc9tME9kOW"
                        },
                        "likeNum": "6005",
                        "pubTime": 1690518192,
                        "reportId": "14181094436820359204:feed:0",
                        "showType": null,
                        "source": {
                            "iconUrl": "https://wx.qlogo.cn/finderhead/ver_1/FqibFPWl9EWSwJicxVbRrABjJ8eibylqzaC0q9IRYfvC5VP3c5AT6WA4FBKomjZEZkfyvJwGp4WFHlw5PW8zicicn5AKgbZXLD1l7zMDhQYxTFNo/132",
                            "mark": [
                                "https://dldir1v6.qq.com/weixin/checkresupdate/icons_filled_channels_authentication_enterprise_a2658032368245639e666fb11533a600.png"
                            ],
                            "title": "中国国家地理"
                        },
                        "jumpInfo": {
                            "extInfo": "{\"behavior\":[\"report_feed_read\",\"allow_pull_top\",\"allow_infinite_top_pull\"],\"encryptedObjectId\":\"export/UzFfAgtgekIEAQAAAAAAWBw2R-03AgAAAAstQy6ubaLX4KHWvLEZgBPE8IM4OQckDYOHzNPgMIpnDF5nVVPB8t43piY_G8Lw\",\"feedFocusChangeNotify\":true,\"feedNonceId\":\"300008098297403665\",\"getRelatedList\":true,\"reportExtraInfo\":\"{\\\"report_json\\\":\\\"\\\"}\\n\",\"reportScene\":14,\"requestScene\":13,\"sessionId\":\"CIOy8JSH3dedxQEI_JDcv8yZ86DFAQjEsLS1ttCNlcUBCJ-wtJ64kIjaxAEIpLDIh5fI1-bEAQj4kczthsffocUBCJew8Pm6n6aexQEI2LDo_K-jyKHFAQjMsKSvvomM9sQBCOeRzI_jhtSVxQEIlLKo-MSU4aHFARD-xqf04_um5AUqBuS4reWbvTAAOICAgICAgAJAAVCft7KBBQ..\"}\n",
                            "feedId": "14181094436820359204",
                            "jumpType": 9
                        },
                        "title": "...#旅行 #四川 #摄影 #地理君带你游<em class=\"highlight\">中国</em>",
                        "videoUrl": "https://findermp.video.qq.com/251/20302/stodownload?encfilekey=6xykWLEnztKcKCJZcV0rWCM8ua7DibZkibqXGfPxf5lropiaiatSQwhdJsTibJBmUiaKCia3QdHxMjjRR6PeWOUzBu4vJVSz8nZiaPH1ja2L7x4iafmwqwF7yoZ7qwJeC1Wt7Stx7uVkghiaSkbHsCGC7vOBs4gkPSJPB4KMlKribpWQWfoiczo&a=1&bizid=1023&dotrans=0&hy=SH&idx=1&m=ed867040f3838690a4b049fe8466cf0f&partscene=4&X-snsvideoflag=W21&token=x5Y29zUxcibDuvYLQPf5C2jzia0oSRPSPVKScSOEmK1gPnYPzw5Y4a9FsewYG99S7qY0HcyD38icicE"
                    }
                ],
                "boxId": "0x80000000000-1-14181094436820359204",
                "type": 86,
                "subType": 1,
                "totalCount": 270
            },
            {
                "items": [
                    {
                        "dateTime": "2小时前",
                        "docId": "14214343629735135480",
                        "duration": "08:03",
                        "image": "http://wxapp.tc.qq.com/251/20304/stodownload?encfilekey=oibeqyX228riaCwo9STVsGLPj9UYCicgttvYkrVgePiaUsbslfAwcgrGvCTnkibv1opiaf3FLjONZeTSvPo2gib2eMXomZ9icUleQCdvoSklNG1GZA2Acwkk0n20DTaKbeibh8v54P01dicpVOiaC4&bizid=1023&dotrans=0&hy=SH&idx=1&m=f1f18e7964afeec730a817b4f27a36b4&token=x5Y29zUxcibBfSvBFHRvY6hRdicrFlWFrowakicsVC5NKS32pXElF90DrR0vNCLG7LE",
                        "imageData": {
                            "height": 1920,
                            "width": 1080,
                            "url": "http://wxapp.tc.qq.com/251/20304/stodownload?encfilekey=oibeqyX228riaCwo9STVsGLPj9UYCicgttvYkrVgePiaUsbslfAwcgrGvCTnkibv1opiaf3FLjONZeTSvPo2gib2eMXomZ9icUleQCdvoSklNG1GZA2Acwkk0n20DTaKbeibh8v54P01dicpVOiaC4&bizid=1023&dotrans=0&hy=SH&idx=1&m=f1f18e7964afeec730a817b4f27a36b4&token=x5Y29zUxcibBfSvBFHRvY6hRdicrFlWFrowakicsVC5NKS32pXElF90DrR0vNCLG7LE"
                        },
                        "likeNum": "44",
                        "pubTime": 1694481805,
                        "reportId": "14214343629735135480:feed:0",
                        "showType": null,
                        "source": {
                            "iconUrl": "http://wx.qlogo.cn/mmhead/Q3auHgzwzM4JATacOGjWWZnGGC5QBiabR7PHSU5NGuAmK2oBUNIpryw/132",
                            "mark": [
                                "https://dldir1v6.qq.com/weixin/checkresupdate/auth_icon_level3_2e2f94615c1e4651a25a7e0446f63135.png"
                            ],
                            "title": "何静说"
                        },
                        "jumpInfo": {
                            "extInfo": "{\"behavior\":[\"report_feed_read\",\"allow_pull_top\",\"allow_infinite_top_pull\"],\"encryptedObjectId\":\"export/UzFfAgtgekIEAQAAAAAAlcgEhwKD4QAAAAstQy6ubaLX4KHWvLEZgBPErKI8UxYrBcSGzNPgMIq4WhW0pTBkkp8LgD6CX9Nc\",\"feedFocusChangeNotify\":true,\"feedNonceId\":\"15033793667473165354\",\"getRelatedList\":true,\"reportExtraInfo\":\"{\\\"report_json\\\":\\\"\\\"}\\n\",\"reportScene\":14,\"requestScene\":13,\"sessionId\":\"CIOy8JSH3dedxQEI_JDcv8yZ86DFAQjEsLS1ttCNlcUBCJ-wtJ64kIjaxAEIpLDIh5fI1-bEAQj4kczthsffocUBCJew8Pm6n6aexQEI2LDo_K-jyKHFAQjMsKSvvomM9sQBCOeRzI_jhtSVxQEIlLKo-MSU4aHFARD-xqf04_um5AUqBuS4reWbvTAAOICAgICAgAJAAVCft7KBBQ..\"}\n",
                            "feedId": "14214343629735135480",
                            "jumpType": 9
                        },
                        "title": "<em class=\"highlight\">中国</em>各省名字的由来～\n#街头采访#何静同学@微信派@微信视频号创造营@微信创作者@微信时刻",
                        "videoUrl": "https://findermp.video.qq.com/251/20302/stodownload?encfilekey=6xykWLEnztKcKCJZcV0rWCM8ua7DibZkibqXGfPxf5lrqdeJe3OZ1M6O2cLicU6cAUuiarGlLZj4wtCLXCMwcF9Ewj7q5gQnKJUcO2PqxzcVQeqr8KoPJFrNY06n1LJWk61cEdTerOq9ib85v71GbUGO48Py2DRLtZEozDl26NCrLOTU&a=1&bizid=1023&dotrans=0&hy=SH&idx=1&m=4560f7f359ffaea8c3ed0065fee80b8c&upid=290280&partscene=4&X-snsvideoflag=W21&token=x5Y29zUxcibDuvYLQPf5C2pZI2r8GAz6F5Jb25WF8aEuKDHHSvRotXAmKicz7yUibru9RcsGo52qFQ"
                    }
                ],
                "boxId": "0x80000000000-1-14214343629735135480",
                "type": 86,
                "subType": 1,
                "totalCount": 270
            },
            {
                "items": [
                    {
                        "dateTime": "2天前",
                        "docId": "14212402730818607127",
                        "duration": "03:36",
                        "image": "http://wxapp.tc.qq.com/251/20304/stodownload?encfilekey=oibeqyX228riaCwo9STVsGLPj9UYCicgttvcJ2bCHkkr5AOXp9ghN5AEONeDJ7GpMu6OZXY7Qo5l2PF61aSJRQQldSzytv9FIkq5uLxg91KbcEUDKZQSdoyuslqalykWcyKMeqB7sBZ1mo&bizid=1023&dotrans=0&hy=SH&idx=1&m=faef1f8a48d09731507254dda7245f15&token=6xykWLEnztKIzBicPuvgFxkT5DDoBlhNqjIAkibjrlNpicwrIPvWcQiaj0IRMveibsF67",
                        "imageData": {
                            "height": 1080,
                            "width": 1920,
                            "url": "http://wxapp.tc.qq.com/251/20304/stodownload?encfilekey=oibeqyX228riaCwo9STVsGLPj9UYCicgttvcJ2bCHkkr5AOXp9ghN5AEONeDJ7GpMu6OZXY7Qo5l2PF61aSJRQQldSzytv9FIkq5uLxg91KbcEUDKZQSdoyuslqalykWcyKMeqB7sBZ1mo&bizid=1023&dotrans=0&hy=SH&idx=1&m=faef1f8a48d09731507254dda7245f15&token=6xykWLEnztKIzBicPuvgFxkT5DDoBlhNqjIAkibjrlNpicwrIPvWcQiaj0IRMveibsF67"
                        },
                        "likeNum": "1266",
                        "pubTime": 1694250432,
                        "reportId": "14212402730818607127:feed:0",
                        "showType": null,
                        "source": {
                            "iconUrl": "https://wx.qlogo.cn/finderhead/ver_1/FqibFPWl9EWSwJicxVbRrABjJ8eibylqzaC0q9IRYfvC5VP3c5AT6WA4FBKomjZEZkfyvJwGp4WFHlw5PW8zicicn5AKgbZXLD1l7zMDhQYxTFNo/132",
                            "mark": [
                                "https://dldir1v6.qq.com/weixin/checkresupdate/icons_filled_channels_authentication_enterprise_a2658032368245639e666fb11533a600.png"
                            ],
                            "title": "中国国家地理"
                        },
                        "jumpInfo": {
                            "extInfo": "{\"behavior\":[\"report_feed_read\",\"allow_pull_top\",\"allow_infinite_top_pull\"],\"encryptedObjectId\":\"export/UzFfAgtgekIEAQAAAAAAcCAJVnOSdAAAAAstQy6ubaLX4KHWvLEZgBPEw4MARypzfPuGzNPgMIp_Z2EYQ4GvYE5SQzrLo26C\",\"feedFocusChangeNotify\":true,\"feedNonceId\":\"8942398082743730121\",\"getRelatedList\":true,\"reportExtraInfo\":\"{\\\"report_json\\\":\\\"\\\"}\\n\",\"reportScene\":14,\"requestScene\":13,\"sessionId\":\"CPyQ3L_MmfOgxQEIxLC0tbbQjZXFAQifsLSeuJCI2sQBCKSwyIeXyNfmxAEI-JHM7YbH36HFAQiXsPD5up-mnsUBCNiw6Pyvo8ihxQEIzLCkr76JjPbEAQjnkcyP44bUlcUBCJSyqPjElOGhxQEIorDco4n24OXEARD-xqf04_um5AUqBuS4reWbvTAAOICAgICAgAJAAVCft7KBBWiUkNzgt5v0xsQB\"}\n",
                            "feedId": "14212402730818607127",
                            "jumpType": 9
                        },
                        "title": "在<em class=\"highlight\">中国</em>广袤的土地上，有着得天独厚的自然之美。不论是山川地貌、风土物种，还是民族文化，总有意想不到的新奇。\n\n除了陆地上的风土人情，作为海洋生物多样性最丰富的国家之一，走入深蓝同样带给人惊喜；深藏在地下的洞穴是这个星球上隐秘的地质奇观，有着非同一般的视觉魅力；沿着河西走廊寻迹，穿越千年的历史长廊，感受着文明的绵长韵味。\n\n出发吧，让我们在路上用眼睛和脚步发现#大美<em class=\"highlight\">中国</em>。#摄影 #旅行 #地理君带你游<em class=\"highlight\">中国</em>",
                        "videoUrl": "https://findermp.video.qq.com/251/20302/stodownload?encfilekey=6xykWLEnztKcKCJZcV0rWCM8ua7DibZkibqXGfPxf5lrovgY0DTc8kLxib7b32Wcuts74sSeCJ8w2svT9tV4VXem55ib4qtXtVaG7MaFVgqLrf597EvdvFiazRPLrPHwzOtmoM8G4ZYtt0OlPBqxnayMKeBL4AnXliarfFaicB2ae2WLUU&a=1&bizid=1023&dotrans=0&hy=SH&idx=1&m=6516ed3be51a3851b8816f49cefa13d6&upid=500030&partscene=4&X-snsvideoflag=W21&token=x5Y29zUxcibDuvYLQPf5C2njeyBTSF3Nv2DRfpK5AicpnObBxmFXRFmIHSMk6iaqWc8vlEdcr9n7yw"
                    }
                ],
                "boxId": "0x80000000000-1-14212402730818607127",
                "type": 86,
                "subType": 1,
                "totalCount": 270
            },
            {
                "items": [
                    {
                        "dateTime": "5小时前",
                        "docId": "14214241248752572504",
                        "duration": "00:08",
                        "image": "http://wxapp.tc.qq.com/251/20304/stodownload?encfilekey=rjD5jyTuFrIpZ2ibE8T7YmwgiahniaXswqznvKdf9Yt2hhicJOL9ficvjLVz5DicpzHRYuKT4KTb2dk1fljVXEDTUGYwx2DCQ33kSfiaNbO7gd0EbcK8LHkiaX9RSQ&bizid=1023&dotrans=0&hy=SH&idx=1&m=&scene=0&token=cztXnd9GyrGhE2iaHGOXDiaEz50vcZdappayTuIPXeToe7hGOyREC70oib2gTCFjF3A",
                        "imageData": {
                            "height": 1920,
                            "width": 1080,
                            "url": "http://wxapp.tc.qq.com/251/20304/stodownload?encfilekey=rjD5jyTuFrIpZ2ibE8T7YmwgiahniaXswqznvKdf9Yt2hhicJOL9ficvjLVz5DicpzHRYuKT4KTb2dk1fljVXEDTUGYwx2DCQ33kSfiaNbO7gd0EbcK8LHkiaX9RSQ&bizid=1023&dotrans=0&hy=SH&idx=1&m=&scene=0&token=cztXnd9GyrGhE2iaHGOXDiaEz50vcZdappayTuIPXeToe7hGOyREC70oib2gTCFjF3A"
                        },
                        "likeNum": "732",
                        "pubTime": 1694469600,
                        "reportId": "14214241248752572504:feed:0",
                        "showType": null,
                        "source": {
                            "iconUrl": "https://wx.qlogo.cn/finderhead/ver_1/AibdpibRqlqLRgICQr0dxdJtBDbeHqqP1SnaSvQvdbUZ2K5wXKViayz6K7QLBh9XFSh6OiaPr2Yn4Y5SZ1Hic8Y4VoWCY28oBUeiar2PglGZnFmUs/132",
                            "mark": [
                                "https://dldir1v6.qq.com/weixin/checkresupdate/auth_icon_level3_2e2f94615c1e4651a25a7e0446f63135.png"
                            ],
                            "title": "前沿科记"
                        },
                        "jumpInfo": {
                            "extInfo": "{\"behavior\":[\"report_feed_read\",\"allow_pull_top\",\"allow_infinite_top_pull\"],\"encryptedObjectId\":\"export/UzFfAgtgekIEAQAAAAAAY-ou_2TqewAAAAstQy6ubaLX4KHWvLEZgBPEjIMYQj9PEsSGzNPgMIpLxBD5k3kjaVgtJ3VQ9Z4p\",\"feedFocusChangeNotify\":true,\"feedNonceId\":\"16046618857466421592\",\"getRelatedList\":true,\"reportExtraInfo\":\"{\\\"report_json\\\":\\\"\\\"}\\n\",\"reportScene\":14,\"requestScene\":13,\"sessionId\":\"CMSwtLW20I2VxQEIn7C0nriQiNrEAQiksMiHl8jX5sQBCPiRzO2Gx9-hxQEIl7Dw-bqfpp7FAQjYsOj8r6PIocUBCMywpK--iYz2xAEI55HMj-OG1JXFAQiUsqj4xJThocUBCKKw3KOJ9uDlxAEItrDMgt7n6KHFARD-xqf04_um5AUqBuS4reWbvTAAOICAgICAgAJAAVCft7KBBQ..\"}\n",
                            "feedId": "14214241248752572504",
                            "jumpType": 9
                        },
                        "title": "<em class=\"highlight\">中国</em>成功测试太赫兹探测装备，所有潜艇将无处可藏#太赫兹#探测装备",
                        "videoUrl": "https://findermp.video.qq.com/251/20302/stodownload?encfilekey=rjD5jyTuFrIpZ2ibE8T7YmwgiahniaXswqztFm6btTjnEsibib0PvvnkibvEvslpBKib2Ej2o39req2cs2iaqjKTLw7mEJ1aHQ33pbNLVYV2qu3ytQEAcwkuzpOvLw&bizid=1023&dotrans=0&hy=SH&idx=1&m=&upid=0&partscene=4&X-snsvideoflag=WT97&token=AxricY7RBHdUkQSDFU11VLPIRiaU6skKzgOlqOf6phHAiafYw1oBvX2GDeuDgBIBdFOrPZOxnYKGww"
                    }
                ],
                "boxId": "0x80000000000-1-14214241248752572504",
                "type": 86,
                "subType": 1,
                "totalCount": 270
            }
        ]
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