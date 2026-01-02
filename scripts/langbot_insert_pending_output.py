import sys
sys.path.append(".")
import time
import argparse
from dao.mongo import MongoDBBase


def main():
    parser = argparse.ArgumentParser(description="Insert a pending LangBot outputmessage for testing.")
    parser.add_argument("--bot-uuid", required=True, help="LangBot bot UUID")
    parser.add_argument("--target-type", choices=["person", "group"], required=True, help="Target type")
    parser.add_argument("--target-id", required=True, help="Target user/group ID")
    parser.add_argument("--text", required=True, help="Text to send")
    args = parser.parse_args()

    mongo = MongoDBBase()
    now = int(time.time())

    doc = {
        "platform": "langbot",
        "status": "pending",
        "message_type": "text",
        "message": args.text,
        "expect_output_timestamp": now,
        "handled_timestamp": None,
        "metadata": {
            "langbot_bot_uuid": args.bot_uuid,
            "langbot_target_type": args.target_type,
            "langbot_target_id": args.target_id,
        },
    }

    inserted_id = mongo.insert_one("outputmessages", doc)
    print(f"Inserted pending outputmessage: {inserted_id}")


if __name__ == "__main__":
    main()

