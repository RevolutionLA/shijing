# 导入必要的库
import re
from collections import defaultdict

# 读取《诗经》文本文件
with open('C:\\Users\\LA-GPT\\Desktop\\LA\\GPT\\shijing\\shijing.txt', 'r', encoding='gbk') as f:
    text = f.read()

# 使用正则表达式提取文本中的汉字
pattern = re.compile(r'[\u4e00-\u9fa5]')
words = pattern.findall(text)

# 使用defaultdict初始化字典，用于存储汉字的频数
frequency = defaultdict(int)

# 统计汉字的频数
for word in words:
    frequency[word] += 1

# 将字典按照频数从大到小排序
sorted_frequency = sorted(frequency.items(), key=lambda x: x[1], reverse=True)

# 计算汉字的频率
total_count = len(words)
for word, count in sorted_frequency:
    frequency[word] = count
    frequency[word + "_freq"] = count / total_count

# 输出汉字的频数和频率
print("汉字频数统计：")
for word, count in sorted_frequency:
    print("汉字：{}，频数：{}".format(word, count))

print("\n汉字频率统计：")
for word, freq in sorted_frequency:
    print("汉字：{}，频率：{:.4%}".format(word, freq / total_count))
