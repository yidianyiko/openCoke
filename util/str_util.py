def remove_chinese(text):
    return "".join(char for char in text if not ("\u4e00" <= char <= "\u9fff"))
