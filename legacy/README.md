# legacy

0.1.0 的三个原始脚本，按原样保留以便溯源，已被 `src/shijing/` 取代。

| 文件 | 原本作用 | 现在由谁负责 |
|---|---|---|
| `shijing_tongji.py` | 字频统计 | `shijing chars` |
| `shijing_ziyun.py` | 字云 | `shijing cloud --kind char` |
| `shijing_ciyun.py` | 词云（jieba） | `shijing cloud --kind word` |

这三个脚本如今**跑不起来**：都写死了 `encoding='gbk'`（数据实际是 UTF-8）和一个
`C:\xxxxxxxxx\shijing.txt` 绝对路径。它们保留在此仅作历史记录，不参与打包、lint 与测试。

对应的数据缺陷（约 61% 整段重复、繁简混排、分组串台、网页表格残留）已在 0.2.0 修复，
详见 [../CHANGELOG.md](../CHANGELOG.md)。
