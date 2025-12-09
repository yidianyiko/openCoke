# -*- coding: utf-8 -*-
"""
多用户压力测试脚本 - 模拟多个微信用户并发通信

功能：
- 模拟多个虚拟用户同时发送消息
- 统计响应时间、成功率等指标
- 支持自定义并发数和消息数量
"""
import sys
sys.path.append(".")

import time
import threading
import random
import uuid
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import List, Dict, Optional

from dao.mongo import MongoDBBase
from dao.user_dao import UserDAO
from bson import ObjectId

# ========== 配置 ==========
# 目标角色 ID（AI 角色）
CHARACTER_ID = "6916d8f79c455f8b8d06ecec"  # Coke

# 压测配置
NUM_VIRTUAL_USERS = 5       # 虚拟用户数量
MESSAGES_PER_USER = 3       # 每个用户发送的消息数
RESPONSE_TIMEOUT = 180       # 等待响应超时时间（秒）
MESSAGE_INTERVAL = 1        # 同一用户消息间隔（秒）

# 测试消息池
TEST_MESSAGES = [
    "你好呀",
    "今天天气怎么样？",
    "在干嘛呢",
    "给我讲个笑话",
    "你喜欢什么",
    "最近有什么好玩的",
    "推荐一部电影",
    "晚上吃什么好",
    "你觉得我怎么样",
    "有什么想对我说的吗",
]


@dataclass
class TestResult:
    """单次测试结果"""
    user_id: str
    user_name: str
    message: str
    send_time: float
    response_time: Optional[float] = None
    response_content: Optional[str] = None
    success: bool = False
    error: Optional[str] = None


@dataclass
class StressTestStats:
    """压测统计"""
    total_messages: int = 0
    successful_responses: int = 0
    failed_responses: int = 0
    total_response_time: float = 0
    min_response_time: float = float('inf')
    max_response_time: float = 0
    results: List[TestResult] = field(default_factory=list)
    
    @property
    def success_rate(self) -> float:
        if self.total_messages == 0:
            return 0
        return self.successful_responses / self.total_messages * 100
    
    @property
    def avg_response_time(self) -> float:
        if self.successful_responses == 0:
            return 0
        return self.total_response_time / self.successful_responses


class VirtualUser:
    """虚拟用户"""
    
    def __init__(self, user_id: str, user_name: str, character_id: str):
        self.user_id = user_id
        self.user_name = user_name
        self.character_id = character_id
        self.mongo = MongoDBBase()
    
    def send_message(self, text: str) -> int:
        """发送消息"""
        now = int(time.time())
        message = {
            "input_timestamp": now,
            "handled_timestamp": now,
            "status": "pending",
            "from_user": self.user_id,
            "platform": "wechat",
            "chatroom_name": None,
            "to_user": self.character_id,
            "message_type": "text",
            "message": text,
            "metadata": {"stress_test": True}
        }
        self.mongo.insert_one("inputmessages", message)
        return now
    
    def wait_for_response(self, timeout: int = 60) -> Optional[Dict]:
        """等待响应"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            now = int(time.time())
            messages = self.mongo.find_many(
                "outputmessages",
                {
                    "platform": "wechat",
                    "from_user": self.character_id,
                    "to_user": self.user_id,
                    "status": "pending",
                    "expect_output_timestamp": {"$lte": now}
                }
            )
            
            if messages:
                msg = messages[0]
                # 标记为已处理
                msg["status"] = "handled"
                msg["handled_timestamp"] = now
                self.mongo.replace_one("outputmessages", {"_id": msg["_id"]}, msg)
                return msg
            
            time.sleep(0.5)
        
        return None
    
    def close(self):
        """关闭连接"""
        self.mongo.close()


class StressTester:
    """压力测试器"""
    
    def __init__(self, character_id: str):
        self.character_id = character_id
        self.user_dao = UserDAO()
        self.mongo = MongoDBBase()
        self.stats = StressTestStats()
        self.virtual_users: List[Dict] = []
        self.lock = threading.Lock()
    
    def create_virtual_users(self, count: int) -> List[Dict]:
        """创建虚拟测试用户"""
        users = []
        
        for i in range(count):
            user_id = str(ObjectId())
            user_name = f"压测用户_{i+1}_{uuid.uuid4().hex[:6]}"
            
            user_data = {
                "_id": ObjectId(user_id),
                "is_character": False,
                "name": user_name,
                "platforms": {
                    "wechat": {
                        "id": f"stress_test_{user_id}",
                        "account": f"stress_{i+1}",
                        "nickname": user_name
                    }
                },
                "status": "normal",
                "user_info": {
                    "tags": ["stress_test"],
                    "created_at": int(time.time())
                }
            }
            
            self.user_dao.create_user(user_data)
            users.append({"user_id": user_id, "user_name": user_name})
            print(f"  创建虚拟用户: {user_name} ({user_id})")
        
        self.virtual_users = users
        return users
    
    def wait_for_messages_processed(self, timeout: int = 30):
        """等待所有消息处理完成（pending -> handled/failed）"""
        user_ids = [u["user_id"] for u in self.virtual_users]
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            pending_count = self.mongo.count_documents(
                "inputmessages",
                {
                    "from_user": {"$in": user_ids},
                    "status": {"$in": ["pending", "handling"]}
                }
            )
            if pending_count == 0:
                print(f"  所有消息已处理完成")
                return
            print(f"  还有 {pending_count} 条消息待处理...")
            time.sleep(2)
        
        print(f"  等待超时，仍有消息未处理")
    
    def cleanup_virtual_users(self):
        """清理虚拟用户"""
        for user in self.virtual_users:
            self.user_dao.delete_user(user["user_id"])
            # 清理相关消息
            self.mongo.delete_many("inputmessages", {"from_user": user["user_id"]})
            self.mongo.delete_many("outputmessages", {"to_user": user["user_id"]})
        print(f"  已清理 {len(self.virtual_users)} 个虚拟用户")
    
    def run_user_test(self, user_info: Dict, messages: List[str]) -> List[TestResult]:
        """运行单个用户的测试"""
        results = []
        virtual_user = VirtualUser(
            user_info["user_id"],
            user_info["user_name"],
            self.character_id
        )
        
        try:
            for msg_text in messages:
                result = TestResult(
                    user_id=user_info["user_id"],
                    user_name=user_info["user_name"],
                    message=msg_text,
                    send_time=time.time()
                )
                
                try:
                    # 发送消息
                    send_ts = virtual_user.send_message(msg_text)
                    print(f"  [{user_info['user_name']}] 发送: {msg_text[:20]}...")
                    
                    # 等待响应
                    response = virtual_user.wait_for_response(RESPONSE_TIMEOUT)
                    
                    if response:
                        result.response_time = time.time() - result.send_time
                        result.response_content = response.get("message", "")[:50]
                        result.success = True
                        print(f"  [{user_info['user_name']}] 收到回复 ({result.response_time:.2f}s): {result.response_content}...")
                    else:
                        result.error = "响应超时"
                        print(f"  [{user_info['user_name']}] 响应超时")
                
                except Exception as e:
                    result.error = str(e)
                    print(f"  [{user_info['user_name']}] 错误: {e}")
                
                results.append(result)
                
                # 消息间隔
                if MESSAGE_INTERVAL > 0:
                    time.sleep(MESSAGE_INTERVAL)
        
        finally:
            virtual_user.close()
        
        return results
    
    def update_stats(self, results: List[TestResult]):
        """更新统计数据"""
        with self.lock:
            for result in results:
                self.stats.total_messages += 1
                self.stats.results.append(result)
                
                if result.success:
                    self.stats.successful_responses += 1
                    self.stats.total_response_time += result.response_time
                    self.stats.min_response_time = min(
                        self.stats.min_response_time, result.response_time
                    )
                    self.stats.max_response_time = max(
                        self.stats.max_response_time, result.response_time
                    )
                else:
                    self.stats.failed_responses += 1
    
    def run_stress_test(self, num_users: int, messages_per_user: int):
        """运行压力测试"""
        print("\n" + "=" * 60)
        print("🚀 多用户压力测试")
        print("=" * 60)
        print(f"  目标角色: {self.character_id}")
        print(f"  虚拟用户数: {num_users}")
        print(f"  每用户消息数: {messages_per_user}")
        print(f"  总消息数: {num_users * messages_per_user}")
        print("=" * 60)
        
        # 创建虚拟用户
        print("\n📝 创建虚拟用户...")
        users = self.create_virtual_users(num_users)
        
        # 为每个用户准备消息
        user_messages = {}
        for user in users:
            user_messages[user["user_id"]] = random.sample(
                TEST_MESSAGES, min(messages_per_user, len(TEST_MESSAGES))
            )
        
        # 并发执行测试
        print("\n🔥 开始并发测试...")
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=num_users) as executor:
            futures = {
                executor.submit(
                    self.run_user_test, user, user_messages[user["user_id"]]
                ): user for user in users
            }
            
            for future in as_completed(futures):
                user = futures[future]
                try:
                    results = future.result()
                    self.update_stats(results)
                except Exception as e:
                    print(f"  [{user['user_name']}] 测试异常: {e}")
        
        total_time = time.time() - start_time
        
        # 打印统计结果
        self.print_stats(total_time)
        
        # 等待所有消息处理完成后再清理
        print("\n⏳ 等待消息处理完成...")
        self.wait_for_messages_processed()
        
        # 清理
        print("\n🧹 清理测试数据...")
        self.cleanup_virtual_users()
        
        self.mongo.close()
        self.user_dao.close()
        
        return self.stats
    
    def print_stats(self, total_time: float):
        """打印统计结果"""
        print("\n" + "=" * 60)
        print("📊 压测结果统计")
        print("=" * 60)
        print(f"  总耗时: {total_time:.2f} 秒")
        print(f"  总消息数: {self.stats.total_messages}")
        print(f"  成功响应: {self.stats.successful_responses}")
        print(f"  失败响应: {self.stats.failed_responses}")
        print(f"  成功率: {self.stats.success_rate:.1f}%")
        
        if self.stats.successful_responses > 0:
            print(f"  平均响应时间: {self.stats.avg_response_time:.2f} 秒")
            print(f"  最小响应时间: {self.stats.min_response_time:.2f} 秒")
            print(f"  最大响应时间: {self.stats.max_response_time:.2f} 秒")
            print(f"  QPS: {self.stats.successful_responses / total_time:.2f}")
        
        print("=" * 60)
        
        # 按用户统计
        print("\n📈 各用户统计:")
        user_stats = {}
        for result in self.stats.results:
            if result.user_name not in user_stats:
                user_stats[result.user_name] = {"success": 0, "fail": 0, "times": []}
            if result.success:
                user_stats[result.user_name]["success"] += 1
                user_stats[result.user_name]["times"].append(result.response_time)
            else:
                user_stats[result.user_name]["fail"] += 1
        
        for user_name, stats in user_stats.items():
            avg_time = sum(stats["times"]) / len(stats["times"]) if stats["times"] else 0
            print(f"  {user_name}: 成功 {stats['success']}, 失败 {stats['fail']}, 平均响应 {avg_time:.2f}s")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="多用户压力测试")
    parser.add_argument("-u", "--users", type=int, default=NUM_VIRTUAL_USERS,
                        help=f"虚拟用户数量 (默认: {NUM_VIRTUAL_USERS})")
    parser.add_argument("-m", "--messages", type=int, default=MESSAGES_PER_USER,
                        help=f"每用户消息数 (默认: {MESSAGES_PER_USER})")
    parser.add_argument("-t", "--timeout", type=int, default=RESPONSE_TIMEOUT,
                        help=f"响应超时时间 (默认: {RESPONSE_TIMEOUT}秒)")
    
    args = parser.parse_args()
    
    # 使用参数中的超时时间
    timeout = args.timeout
    
    tester = StressTester(CHARACTER_ID)
    tester.run_stress_test(args.users, args.messages)


if __name__ == "__main__":
    main()
