"""
清除数据库中所有用户的聊天记录
警告：此操作不可逆，请谨慎执行！
"""
import sys
sys.path.append(".")

from dao.conversation_dao import ConversationDAO


def clear_all_conversations():
    """删除所有会话记录"""
    dao = ConversationDAO()
    
    try:
        # 统计当前会话数量
        total_count = dao.count_conversations()
        print(f"当前数据库中共有 {total_count} 条会话记录")
        
        if total_count == 0:
            print("数据库中没有会话记录，无需清理")
            return
        
        # 二次确认
        confirm = input(f"确定要删除所有 {total_count} 条会话记录吗？此操作不可逆！(输入 'yes' 确认): ")
        
        if confirm.lower() != 'yes':
            print("操作已取消")
            return
        
        # 删除所有会话
        deleted_count = dao.collection.delete_many({}).deleted_count
        print(f"成功删除 {deleted_count} 条会话记录")
        
    except Exception as e:
        print(f"删除失败: {e}")
    finally:
        dao.close()


if __name__ == "__main__":
    print("=" * 50)
    print("警告：此脚本将删除数据库中所有用户的聊天记录！")
    print("=" * 50)
    clear_all_conversations()
