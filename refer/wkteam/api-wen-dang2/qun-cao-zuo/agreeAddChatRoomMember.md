- 群管理确认入群邀请

## 群管理确认入群邀请

[!DANGER]

- 本接口需管理员方可调用，因群开启邀请确认，需管理员调用本接口同意新成员，方可入群

请求URL：

- http://域名/agreeAddChatRoomMember

请求方式：

- POST

请求头Headers：

- Content-Type：application/json
- Authorization：login接口返回

参数：

| 参数名 | 必选 | 类型 | 说明 |
| wId | 是 | String | 登录实例标识 |
| chatRoomId | 是 | String | 群id |
| newMsgId | 是 | number | 入群邀请回调返回newmMsgid |
| xml | 是 | String | 入群邀请的回调xml |

请求参数示例

```
{
    "wId": "2c7a5bf6-e23d-4fb0-8f03-b90e844b539f",
    "chatRoomId": "18061832422@chatroom",
    "newMsgId": 7175333311063873621,
    "xml":"<sysmsg type=\"NewXmlChatRoomAccessVerifyApplication\">\n\t<NewXmlChatRoomAccessVerifyApplication>\n\t\t<text><![CDATA[\"朝夕\"想邀请1位朋友加入群聊]]></text>\n\t\t<link>\n\t\t\t<scene>roomaccessapplycheck_approve</scene>\n\t\t\t<text><![CDATA[  去确认]]></text>\n\t\t\t<ticket><![CDATA[AQAAAAEAAAAYoqpRKaJIGP+bvAGdxtKlyNkkBVxU4H4VjouTQFRqPDcWj8jNkBE/MSS9AQs1tk/deahMXMaXyL02CI54LTyctebq3g==]]></ticket>\n\t\t\t<invitationreason><![CDATA[8888888]]></invitationreason>\n\t\t\t<inviterusername><![CDATA[zhangchuan2288]]></inviterusername>\n\t\t\t<memberlist>\n\t\t\t\t<memberlistsize>1</memberlistsize>\n\t\t\t\t<member>\n\t\t\t\t\t<username><![CDATA[wxid_phyyedw9xap22]]></username>\n\t\t\t\t\t<nickname><![CDATA[我们一起笑。]]></nickname>\n\t\t\t\t\t<headimgurl><![CDATA[http://wx.qlogo.cn/mmhead/ver_1/QVH2YybBlUaH18IX7UC3YYpX2GFdUgK7sVdjGIzzyMH6FBoGx53Pv7R7netr5tzw4g8icTy4HrP4UrA3easfjjlzBP8iccUUVlQCFJ3y8fNfU/132]]></headimgurl>\n\t\t\t\t</member>\n\t\t\t</memberlist>\n\t\t</link>\n\t\t<RoomName><![CDATA[18061832422@chatroom]]></RoomName>\n\t</NewXmlChatRoomAccessVerifyApplication>\n</sysmsg>"
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