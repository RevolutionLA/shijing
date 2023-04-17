import matplotlib.pyplot as plt
from wordcloud import WordCloud
from collections import Counter

# 读取《诗经》文本文件，使用 'gbk' 编码方式解码
with open('C:\\xxxxxxxxxxxxxxxxx\\shijing.txt', 'r', encoding='gbk') as f:
    text = f.read()

# 统计每个汉字的频数
counter = Counter(text)

# 获取汉字和频数
words = list(counter.keys())
word_frequencies = list(counter.values())

# 创建词云对象，并设置词云参数
wordcloud = WordCloud(font_path='simhei.ttf', width=800, height=600, 
                      background_color='white', max_words=200, 
                      prefer_horizontal=1, mode='RGBA', 
                      relative_scaling=0.5).generate_from_frequencies(counter)

# 根据字的出现概率设置字体大小
wordcloud = WordCloud(font_path='simhei.ttf', width=800, height=600, 
                      background_color='white', max_words=200, 
                      prefer_horizontal=1, mode='RGBA', 
                      relative_scaling=0.5).generate_from_frequencies(counter)

# 绘制词云图片
plt.figure(figsize=(10, 6))
plt.imshow(wordcloud, interpolation='bilinear')
plt.axis('off')
plt.show()
