- 获取个人主页

## 获取个人主页

请求URL：

- http://域名/finderHome

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |

请求参数示例

```
{
    "wId": "2c7a5bf6-e23d-x-8f03-b90e844b539f"
}

```

成功返回示例

```
{
    "code": "1000",
    "message": "处理成功",
    "data": {
        "userName": "v2_060000231003b20faec03ec3db0776955d3d97c6b329d6aa58693bcdb7ad1@finder",
        "aliasInfo": [
            {
                "nickName": "朝夕",
                "headImgUrl": "http://wx.qlogo.cn/mmhead/Q3auHgzwzM5grqOsJtnHiaiapZ4cv43GNBzh1sA8NGkwbrvI7Kg3vTcQ/0",
                "roleType": 1
            },
            {
                "nickName": "朝夕v",
                "headImgUrl": "http://wx.qlogo.cn/finderhead/Q3auHgzwzM5grqOsJtnHiaiapZ4cv43GNBJkH0guXYeulzge7e7IQwHg/0",
                "roleType": 3
            }
        ],
        "currentAliasRoleType": 3,
        "finderList": [
            "CgASqwIKVnYyXzA2MDAwMDIzMTAwM2IyMGZhZWM4YzZlMThmMTBjN2Q2YzkwM2VjM2RiMDc3Njk1NWQzZDk3YzZiMzI5ZDZhYTU4NjkzYmNkYjdhZDFAZmluZGVyEgfmnJ3lpJV2GpUBaHR0cDovL3d4LnFsb2dvLmNuL2ZpbmRlcmhlYWQvdmVyXzEvUHhPTUk0MnFtUjY4eEJqdEFXbXJocEtYbndVd0QwdW8xQUxlWTJsaWNpY3BBeWtLaWNhQmVOZnVOeEhOSnRuZEhyZEc3RElYcTRtRE11RlhGS2Z6anloUmU5RnhsUmZ2Z1hqRWliYU5VakJFU3VJLzAgACoAQgBKAFAAWIiAEGICIAFyAhACeAKSAQCyAREIgBEQ36cBGAAiBAgAEAQqALACACIzCAAQAhoAIhNnaF80ZWYxYjY4ODRmYjJAYXBwKhZwYWdlcy9pbmRleC9pbmRleC5odG1sKi0KEnd4MmJmZjg3OGM1MWJhYjIzYhIXL3BhZ2VzL2luZGV4L2luZGV4Lmh0bWxAB0pDaHR0cHM6Ly9jaGFubmVscy53ZWl4aW4ucXEuY2pbmcvaW5kZXg/dHlwZT1tcApaGg/mm7TmjaLnrqHnkIblkZggAipFaHR0cHM6Ly9jaGFubmVscy53ZWl4aW4ucXEuY29tL3BhbmRvcmEvcGFnZXMvYml6LWJpbmRpbmcvY2hhbmdlYWRtaW4vCmcaFee7keWumueahOS8geS4muW+ruS/oSACKkxodHRwczovL2NoYW5uZWxzLndlaXhpbi5xcS5jb20vbW9iaWxlLXN1cHBvcnQvcGFnZXMvYml6LWJpbmRpbmcvaW5kZXg/dHlwZT03Cm0aG+e7keWumueahOihqOaDheW8gOaUvuW5s+WPsCACKkxodHRwczovL2NoYW5uZWxzLndlaXhpbi5xcS5jb20vbW9iaWxlLXN1cHBvcnQvcGFnZXMvYml6LWJpbmRpbmcvaW5kZXg/dHlwZT05clbop4bpopHlj7flkI3lrZflsIbkv67mlLnkuLrigJwkbmlja25hbWUk4oCd77yM5L+u5pS55ZCO5LuK5bm05Ymp5L2ZNeasoeS/ruaUueacuuS8muOAgno5EjdodHRwczovL2NoYW5uZWxzLndlaXhpbi5xcS5jb20vbWNuL21vYmlsZS93aXRoZHJhdy5odG1smgE1EjMKEnd4MmJmZjg3OGM1MWJhYjIzYhABGhsvcGFnZXMvcHJlcmVuZGVyL2luZGV4Lmh0bWyqARnku4rlubTov5jlj6/kv67mlLk15qyh44CCsAECuAEC2gEQ5pio5pelMOasoeaSreaUvg==",
            "CgASrgIKVnYyXzA2MDAwMDIzMTAwM2IyMGZhZWM4YzZlNzhhMWZjMmQzY2QwNmViMzBiMDc3YzU1ODdiNzljYjU2YjAzZjEyYTMyZmNjOGI3N2Y5ZTdAZmluZGVyEgjmnJ3lpJV2dhqZAWh0dHA6Ly93eC5xbG9nby5jbi9maW5kZXJoZWFkL3Zlcl8xLzFsa1dkbGVrN0NYTmtRQnFhTWlibzBoTzdxR09RVmJ1SnEyU2JHTk5td1pKbWlhblppYXl4YVJCc1FGRWdZYmljNHFpY0ZpY0F1VXB6c0I4QWlhMHhVV0hqYUVCNDdLNUJMWWppY1hBMFF5TEQ4blc0ckJhYjIzYhIXL3BhZ2VzL2luZGV4L2luZGV4Lmh0bWxAB0pDaHR0cHM6Ly9jaGFubmVscy53ZWl4aW4ucXEuY29tL2Fzc2lzdGFudC1zdXBwb3J0L3BhZ2VzL2NyZWF0b3ItaG9tZXJW6KeG6aKR5Y+35ZCN5a2X5bCG5L+u5pS55Li64oCcJG5pY2tuYW1lJOKAne+8jOS/ruaUueWQjuS7iuW5tOWJqeS9mTXmrKHkv67mlLnmnLrkvJrjgIJ6ORI3aHR0cHM6Ly9jaGFubmVscy53ZWl4aW4ucXEuY29tL21jbi9tb2JpbGUvd2l0aGRyYXcuaHRtbJoBNRIzChJ3eDJiZmY4NzhjNTFiYWIyM2IQARobL3BhZ2VzL3ByZXJlbmRlci9pbmRleC5odG1sqgEZ5LuK5bm06L+Y5Y+v5L+u5pS5NeasoeOAgrABArgBAcABAdoBEOaYqOaXpTDmrKHmkq3mlL4="
        ],
        "showInWxFinderUsername": "v2_060000231003b20ffc2d3cd06eb30b077c5587b79cb56b03f12a32fcc8b77f9e7@finder"
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