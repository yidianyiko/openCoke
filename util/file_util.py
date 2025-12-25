import sys

import pysilk

sys.path.append(".")

import logging
import traceback
from logging import getLogger

logging.basicConfig(level=logging.INFO)
logger = getLogger(__name__)


def pcm_to_silk(file_path, bit_rate=128000, sample_rate=24000):
    new_file_path = file_path.replace(".pcm", ".silk")

    with open(new_file_path, "wb") as new_f:
        with open(file_path, "rb") as f:
            pysilk.encode(f, new_f, sample_rate=sample_rate, bit_rate=bit_rate)

    return new_file_path


# 使用示例
if __name__ == "__main__":
    try:
        path = pcm_to_silk("framework/tool/text2voice/test.pcm")
        print("转换成功！")
    except Exception:
        logger.error(traceback.format_exc())
